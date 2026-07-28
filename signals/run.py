"""On-demand pipeline: scan symbols, confirm setups via LLM, store signals.

Usage: python -m signals.run
"""
import os
import random
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import NamedTuple

import requests

from signals.market_client import fetch_candles
from signals.chart.pipeline import attach_chart
from signals.composer import confirm_setup, no_setup_rationale
from signals.rag import retrieve_context
from signals.config import load_config
from signals.indicators import adx, atr, ema, macd_histogram, rsi
from signals.debate import run_debate
from signals.llm_client import SeaLionClient
from signals.models import (
    DEFAULT_SIGNAL_STRATEGY,
    TIMEFRAME_MINUTES,
    TRADING_SESSIONS,
    CandidateSetup,
    Confirmation,
    NoSignalReport,
    ScanResult,
    make_signal,
)
from signals.outcome_tracker import track_open_signals
from signals.session_clock import describe_market_session
from signals.strategies import detect_setup
from signals.storage import (
    fetch_bot_settings,
    latest_ai_event_time,
    latest_ai_event_times_since,
    latest_signal,
    latest_signals_since,
    open_symbols_for_timeframe,
    release_engine_lock,
    save_ai_event,
    save_debate,
    save_engine_run,
    save_signal,
    try_acquire_engine_lock,
)
from signals.telegram_client import send_alert

RETRY_DELAY = 2.0

# Sentinel: prefetch failed — callers must fail closed (skip / block).
PREFETCH_UNAVAILABLE = object()

# Scans are I/O-bound (Binance, SEA-LION, Supabase), so symbols run in
# parallel. Each worker gets its own requests.Session and LLM client —
# neither is thread-safe to share.
MAX_SCAN_WORKERS = 4

# The detector flags a crossover on any of the last DEDUP_BARS bars, so runs
# closer together than that would re-store the same setup. The window scales
# with each session's timeframe (3 bars of 15m = 45m; 3 bars of 1h = 3h) so
# scalp and swing each dedup against their own bar size.
DEDUP_BARS = 3


def _dedup_window(timeframe: str) -> timedelta:
    minutes = TIMEFRAME_MINUTES.get(timeframe, TIMEFRAME_MINUTES["1h"])
    return timedelta(minutes=minutes * DEDUP_BARS)


# The engine is invoked far more often (~every 10 min, via external cron and
# the GitHub Actions backup schedule) than either session's own bar closes.
# Without this throttle every run re-evaluates a symbol against the *same*
# still-open candle, producing identical LLM rationale and duplicate
# no-signal/rejected Telegram alerts run after run. Skip re-evaluating a
# (symbol, timeframe) until most of its own bar has elapsed since the last
# logged outcome — 90% of the bar, so a slightly early cron tick still
# lands inside the window instead of missing it by a few minutes.
EVAL_THROTTLE_FRACTION = 0.9


def _prefetch_recent_events(symbols, timeframe, cfg, session=None):
    """One batched query replacing what would otherwise be one
    latest_ai_event_time lookup per symbol in `symbols`. Returns
    PREFETCH_UNAVAILABLE on failure so callers fail closed."""
    minutes = TIMEFRAME_MINUTES.get(timeframe, TIMEFRAME_MINUTES["1h"])
    since = (datetime.now(timezone.utc)
             - timedelta(minutes=minutes * EVAL_THROTTLE_FRACTION)).isoformat()
    try:
        return latest_ai_event_times_since(
            symbols, timeframe, since, cfg.supabase_url,
            cfg.supabase_service_key, session=session,
        )
    except Exception as exc:
        print(f"recency batch check failed ({type(exc).__name__}), skipping evals")
        return PREFETCH_UNAVAILABLE


def _prefetch_recent_signals(symbols, timeframe, cfg, session=None):
    """Batched dedup map; PREFETCH_UNAVAILABLE on failure (fail closed)."""
    since = (datetime.now(timezone.utc) - _dedup_window(timeframe)).isoformat()
    try:
        return latest_signals_since(
            symbols, timeframe, since, cfg.supabase_url,
            cfg.supabase_service_key, session=session,
        )
    except Exception as exc:
        print(f"dedup batch check failed ({type(exc).__name__}), blocking stores")
        return PREFETCH_UNAVAILABLE


def _prefetch_open_symbols(symbols, timeframe, cfg, session=None):
    """Symbols that already have an open signal on this timeframe."""
    try:
        return open_symbols_for_timeframe(
            symbols, timeframe, cfg.supabase_url, cfg.supabase_service_key,
            session=session,
        )
    except Exception as exc:
        print(f"open-signal batch check failed ({type(exc).__name__}), blocking stores")
        return PREFETCH_UNAVAILABLE


def _recently_evaluated(symbol, timeframe, cfg, session=None,
                        recent_events=None) -> bool:
    """True when this (symbol, timeframe) already produced a logged outcome
    within its throttle window. Fail closed on lookup failure — skip the
    symbol rather than re-evaluating without knowing recency."""
    if recent_events is PREFETCH_UNAVAILABLE:
        return True
    if recent_events is not None:
        last = recent_events.get(symbol)
    else:
        try:
            last = latest_ai_event_time(symbol, timeframe, cfg.supabase_url,
                                        cfg.supabase_service_key, session=session)
        except Exception as exc:
            print(f"[{symbol}] recency check failed ({type(exc).__name__}), skipping")
            return True
    if last is None:
        return False
    minutes = TIMEFRAME_MINUTES.get(timeframe, TIMEFRAME_MINUTES["1h"])
    threshold = timedelta(minutes=minutes * EVAL_THROTTLE_FRACTION)
    elapsed = datetime.now(timezone.utc) - datetime.fromisoformat(last)
    return elapsed < threshold


def with_retry(fn, attempts=2, delay=None):
    """Call fn; on failure wait `delay` seconds and try once more per extra attempt.

    delay=None resolves to the module-level RETRY_DELAY at call time.
    """
    if delay is None:
        delay = RETRY_DELAY
    last_error = None
    for attempt in range(attempts):
        try:
            return fn()
        except Exception as exc:
            last_error = exc
            if attempt < attempts - 1:
                time.sleep(delay)
    raise last_error


def already_signaled(setup, cfg, timeframe="1h", session=None,
                     recent_signals=None, open_symbols=None):
    """True when a new signal must not be stored: an open position already
    exists for this symbol+timeframe, or the newest stored signal duplicates
    the candidate (same direction within the dedup window). Fail closed on
    lookup failure — better a missed signal than a duplicate stack."""
    if open_symbols is PREFETCH_UNAVAILABLE or recent_signals is PREFETCH_UNAVAILABLE:
        return True
    if open_symbols is not None and setup.symbol in open_symbols:
        return True
    if recent_signals is not None:
        row = recent_signals.get(setup.symbol)
    else:
        try:
            row = latest_signal(setup.symbol, cfg.supabase_url,
                                cfg.supabase_service_key, timeframe=timeframe,
                                session=session)
        except Exception as exc:
            print(f"[{setup.symbol}] dedup check failed "
                  f"({type(exc).__name__}), blocking store")
            return True
    if row is None:
        return False
    # Prefer status when present (open rows always block).
    if row.get("status") == "open":
        return True
    if row["direction"] != setup.direction:
        return False
    stored_at = datetime.fromisoformat(row["created_at"])
    return datetime.now(timezone.utc) - stored_at < _dedup_window(timeframe)


def _latest_indicators(ema9, ema21, rsi14, macd_hist):
    if None in (ema9[-1], ema21[-1], rsi14[-1], macd_hist[-1]):
        return None
    return {
        "ema9": ema9[-1],
        "ema21": ema21[-1],
        "rsi": rsi14[-1],
        "macd_hist": macd_hist[-1],
    }


# Just enough candles for EMA21 to warm up plus a little history — this is
# only a trend-direction read, not a full setup scan.
HTF_TREND_CANDLE_LIMIT = 30


def _fetch_htf_trend(symbol, timeframe, cfg, session=None):
    """"up"/"down" trend on a higher timeframe, from EMA9 vs EMA21.
    Returns None when EMAs are equal / still warming up.
    Raises RuntimeError when market data cannot be fetched so callers that
    require confluence can fail closed."""
    candles = with_retry(lambda: fetch_candles(
        symbol, timeframe, HTF_TREND_CANDLE_LIMIT, session=session))
    candles = candles[:-1]  # drop the still-forming candle, same as the main fetch
    closes = [c.close for c in candles]
    fast = ema(closes, 9)
    slow = ema(closes, 21)
    if fast[-1] is None or slow[-1] is None:
        return None
    if fast[-1] > slow[-1]:
        return "up"
    if fast[-1] < slow[-1]:
        return "down"
    return None


def _log_ai_event(kind: str, symbol: str, cfg, *, timeframe: str,
                  rationale: str, indicators: dict, headlines: list,
                  direction=None, entry=None, stop_loss=None, take_profit=None,
                  confidence=None, session=None) -> None:
    """Best-effort insert into ai_events; never raises."""
    event = {
        "id": str(uuid.uuid4()),
        "symbol": symbol,
        "timeframe": timeframe,
        "kind": kind,
        "direction": direction,
        "entry": entry,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "confidence": confidence,
        "rationale": rationale,
        "indicators": indicators,
        "news_headlines": list(headlines),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        with_retry(lambda: save_ai_event(
            event, cfg.supabase_url, cfg.supabase_service_key, session=session,
        ))
    except Exception as exc:
        print(f"[{symbol}] failed to store ai_events ({type(exc).__name__}), continuing")


def _reject(symbol, cfg, *, timeframe, report_kind, event_kind, rationale,
            indicators, candles, setup=None, confidence=None, session=None):
    """Log a no-setup/reject ai_event and return the matching ScanResult.

    Trade fields (direction/entry/stop_loss/take_profit) come from `setup` when
    present, else None. `report_kind` is the NoSignalReport kind ("no_setup" /
    "rejected"); `event_kind` is the ai_events kind ("no_setup" / "reject").
    """
    direction = setup.direction if setup is not None else None
    entry = setup.entry if setup is not None else None
    stop_loss = setup.stop_loss if setup is not None else None
    take_profit = setup.take_profit if setup is not None else None
    _log_ai_event(
        event_kind, symbol, cfg, timeframe=timeframe, rationale=rationale,
        indicators=indicators, headlines=[], direction=direction, entry=entry,
        stop_loss=stop_loss, take_profit=take_profit, confidence=confidence,
        session=session,
    )
    return ScanResult(no_signal=NoSignalReport(
        symbol=symbol, timeframe=timeframe, kind=report_kind, rationale=rationale,
        indicators=indicators, direction=direction, entry=entry,
        stop_loss=stop_loss, take_profit=take_profit, confidence=confidence,
    ), candles=candles)


# Fraction of LLM-rejected setups recorded as shadow signals for the
# confirmation-gate A/B (docs/superpowers/specs/2026-07-26-ai-gate-ab-design.md).
#
# Defaults to 0.0 — OFF. A shadow row is only safe once the RLS migration at
# the end of supabase/schema.sql has been applied AND
# scripts/verify_shadow_rls.py passes; until then a shadow would be publicly
# visible on the track record. Set SHADOW_SAMPLE_RATE=0.25 to start the
# experiment. Rejects arrive ~7x faster than confirms and the confirmed arm is
# the statistical bottleneck, so sampling here costs no experiment time while
# keeping storage and outcome-tracker load roughly flat.
SHADOW_SAMPLE_RATE = float(os.environ.get("SHADOW_SAMPLE_RATE", "0.0"))


def _shadow_sampled() -> bool:
    """Whether to record this rejected setup.

    Random, and deliberately NOT keyed on confidence, symbol or strategy —
    sampling on any of those would bias the very arm being measured.
    """
    return random.random() < SHADOW_SAMPLE_RATE


def _save_shadow(setup, confirmation, cfg, *, timeframe, session):
    """Record an LLM-rejected setup so the gate's accuracy is measurable.

    A shadow signal is outcome-tracked exactly like a real one but is filtered
    out of every user-facing read path — it is not a recommendation. Failures
    are swallowed: the experiment must never break a live scan.
    """
    if not _shadow_sampled():
        return
    try:
        shadow = make_signal(setup, confirmation, [], timeframe=timeframe)
        save_signal(shadow, cfg.supabase_url, cfg.supabase_service_key,
                    session=session, shadow=True, experiment="gate_ab")
    except Exception as exc:
        print(f"shadow save failed ({type(exc).__name__}) — continuing")


# Paper trial: limit-entry S/R at 1h, the only configuration that measured net
# positive once each entry style was paired with the fee tier it can actually
# achieve (+0.065R at maker rates; market entry is always taker). Recorded, not
# delivered — it exists to check the backtest result on forward data before any
# signal-lifecycle work. OFF by default.
PAPER_SR_LIMIT = os.environ.get("PAPER_SR_LIMIT", "").lower() in ("1", "true")
PAPER_SR_LIMIT_TIMEFRAME = "1h"


def _record_paper_sr_limit(symbol, market, cfg, *, timeframe, session):
    """Record a limit-entry S/R setup as an undelivered paper signal.

    Deliberately skips the LLM, Telegram and chart rendering: this measures the
    rules, and adding the gate would confound it with the other live
    experiment. Failures are swallowed — a paper trial must never break a scan.
    """
    if not PAPER_SR_LIMIT or timeframe != PAPER_SR_LIMIT_TIMEFRAME:
        return
    try:
        from signals.strategies.sr_limit import detect_setup as detect_limit

        setup = detect_limit(
            symbol, market.candles, market.atr14,
            adx14=market.adx14, htf_trend=market.htf_trend,
        )
        if setup is None:
            return
        paper = make_signal(
            setup, Confirmation("confirm", 0, "paper trial — not delivered"),
            [], timeframe=timeframe,
        )
        save_signal(paper, cfg.supabase_url, cfg.supabase_service_key,
                    session=session, shadow=True, experiment="sr_limit")
    except Exception as exc:
        print(f"paper sr_limit save failed ({type(exc).__name__}) — continuing")


# Paper trial: BBMA Re-entry, the one pattern that survived a nine-year test
# (docs/bbma-backtest-results.md). Over 2017-08 to 2026-06 on BTC and ETH it
# returned +0.120R net across 905 trades, profitable in 7 of 10 calendar years
# with a positive median and only 18% of its total from its top ten trades. Its
# best years were the 2018 bear and the 2020 crash. Nothing was tuned: the
# parameters were fixed before the long history was ever loaded.
#
# WHY 1h AND NOT 4h. 4h measured stronger (+0.250R vs +0.089R) because a wider
# stop makes cost a smaller fraction of R. But 4h fires ~12 times per symbol
# per year, so a readable forward sample would take upwards of two years. 1h
# fires ~38, and the swing session already scans 1h against a 4h confluence
# trend — which is exactly the configuration the backtest measured, at no extra
# fetch. The weaker-but-readable arm is the one worth running forward.
#
# Recorded, never delivered. OFF by default.
PAPER_BBMA_REENTRY = os.environ.get(
    "PAPER_BBMA_REENTRY", "").lower() in ("1", "true")
PAPER_BBMA_REENTRY_TIMEFRAME = "1h"


def _record_paper_bbma_reentry(symbol, market, cfg, *, timeframe, session):
    """Record a BBMA Re-entry setup as an undelivered paper signal.

    Skips the LLM, Telegram and chart rendering for the same reason
    `_record_paper_sr_limit` does: this measures the rules on forward data, and
    running the confirmation gate over it would confound this trial with the
    gate A/B. Failures are swallowed — a paper trial must never break a scan.
    """
    if not PAPER_BBMA_REENTRY or timeframe != PAPER_BBMA_REENTRY_TIMEFRAME:
        return
    try:
        from signals.strategies.bbma import detect_reentry

        setup = detect_reentry(
            symbol, market.candles, market.atr14,
            adx14=market.adx14, htf_trend=market.htf_trend,
        )
        if setup is None:
            return
        paper = make_signal(
            setup, Confirmation("confirm", 0, "paper trial — not delivered"),
            [], timeframe=timeframe,
        )
        save_signal(paper, cfg.supabase_url, cfg.supabase_service_key,
                    session=session, shadow=True, experiment="bbma_reentry")
    except Exception as exc:
        print(f"paper bbma_reentry save failed ({type(exc).__name__}) — continuing")


def _no_setup_indicators(strategy, atr14, adx14, htf_trend,
                         ema9, ema21, rsi14, macd_hist):
    """Indicators to attach to a no-setup ai_event, or None while a required
    series is still warming up (mirrors the previous per-strategy branches)."""
    if strategy in ("ict_smc", "ict_fvg", "sr_zone"):
        if atr14[-1] is None:
            return None
        indicators = {"strategy": strategy, "atr": atr14[-1]}
        # ict_fvg intentionally omits ADX (matches prior behavior).
        if strategy != "ict_fvg" and adx14[-1] is not None:
            indicators["adx"] = adx14[-1]
        if htf_trend is not None:
            indicators["htf_trend"] = htf_trend
        return indicators
    if strategy == "ce_lwma":
        return {"strategy": "ce_lwma"}
    return _latest_indicators(ema9, ema21, rsi14, macd_hist)


class MarketData(NamedTuple):
    candles: list
    ema9: list
    ema21: list
    rsi14: list
    macd_hist: list
    atr14: list
    adx14: list
    htf_trend: object
    h1_candles: object


def _load_market_data(symbol, timeframe, strategy, cfg, *,
                      confluence_timeframe=None, session=None):
    """Fetch closed candles + indicators (+ H1 for ce_lwma / HTF trend for
    confluence). Returns (MarketData, candles) on success, (None, None) when the
    initial candle fetch fails, or (None, candles) when a required H1/HTF fetch
    fails after candles were already fetched."""
    candle_limit = max(cfg.candle_limit, 220) if strategy == "ce_lwma" else cfg.candle_limit
    try:
        candles = with_retry(
            lambda: fetch_candles(symbol, timeframe, candle_limit, session=session)
        )
    except Exception as exc:
        print(f"[{symbol}] market data unavailable, skipping: {exc}")
        return None, None

    candles = candles[:-1]
    closes = [c.close for c in candles]
    highs = [c.high for c in candles]
    lows = [c.low for c in candles]
    ema9 = ema(closes, 9)
    ema21 = ema(closes, 21)
    rsi14 = rsi(closes, 14)
    macd_hist = macd_histogram(closes)
    atr14 = atr(highs, lows, closes, 14)
    adx14 = adx(highs, lows, closes, 14)
    htf_trend = None
    h1_candles = None
    if strategy == "ce_lwma":
        try:
            h1_raw = with_retry(
                lambda: fetch_candles(symbol, "1h", max(cfg.candle_limit, 80),
                                      session=session)
            )
            h1_candles = h1_raw[:-1]
        except Exception as exc:
            print(f"[{symbol}] H1 CE data unavailable ({type(exc).__name__}), "
                  "skipping")
            return None, candles
    elif confluence_timeframe:
        try:
            htf_trend = _fetch_htf_trend(symbol, confluence_timeframe, cfg,
                                         session=session)
        except Exception as exc:
            print(f"[{symbol}] HTF confluence required but unavailable "
                  f"({type(exc).__name__}), skipping")
            return None, candles

    return MarketData(candles=candles, ema9=ema9, ema21=ema21, rsi14=rsi14,
                      macd_hist=macd_hist, atr14=atr14, adx14=adx14,
                      htf_trend=htf_trend, h1_candles=h1_candles), candles


def scan_symbol(symbol, cfg, llm, *, strategy=DEFAULT_SIGNAL_STRATEGY,
                timeframe=None,
                session=None,
                recent_events=None, recent_signals=None,
                open_symbols=None, confluence_timeframe=None,
                min_store_confidence=0, skip_recency=False, log_no_setup=True):
    """Scan one symbol on one session's timeframe; return a ScanResult with
    a stored signal or a no-signal report.

    `timeframe` selects the session (e.g. "15m" scalp, "1h" swing);
    defaults to cfg.timeframe for single-session callers. The review is
    purely technical — no news or economic-calendar inputs.
    `recent_events`/`recent_signals`/`open_symbols` are this session's
    prefetched maps; when None each check falls back to its own
    per-symbol query. `confluence_timeframe`, when given, requires a
    successful HTF trend read and gates setups on agreement.
    `min_store_confidence` drops LLM confirms below the admin quality bar
    before they hit storage (not just Telegram). `skip_recency` bypasses the
    "evaluated recently" throttle (for the 1m scalper, which fires every
    minute); `log_no_setup=False` suppresses the no-setup ai_event so a
    high-frequency scan does not flood the log.
    """
    timeframe = timeframe or cfg.timeframe

    if not skip_recency and _recently_evaluated(
            symbol, timeframe, cfg, session=session, recent_events=recent_events):
        print(f"[{symbol}] {timeframe} evaluated recently, skipping this run")
        return ScanResult()

    market, candles = _load_market_data(
        symbol, timeframe, strategy, cfg,
        confluence_timeframe=confluence_timeframe, session=session,
    )
    if market is None:
        return ScanResult(candles=candles)
    candles = market.candles
    ema9, ema21 = market.ema9, market.ema21
    rsi14, macd_hist = market.rsi14, market.macd_hist
    atr14, adx14 = market.atr14, market.adx14
    htf_trend, h1_candles = market.htf_trend, market.h1_candles

    # Paper trial runs off the same market data, before and independently of
    # the live strategy — it must not influence what gets delivered.
    _record_paper_sr_limit(symbol, market, cfg,
                           timeframe=timeframe, session=session)
    _record_paper_bbma_reentry(symbol, market, cfg,
                               timeframe=timeframe, session=session)

    setup = detect_setup(
        strategy, symbol, candles, ema9, ema21, rsi14, macd_hist, atr14,
        adx14=adx14, htf_trend=htf_trend, h1_candles=h1_candles,
    )
    if setup is None:
        print(f"[{symbol}] no setup found ({strategy})")
        # High-frequency callers (the 1m scalper) suppress the no-setup event
        # so 60 quiet scans/hour don't flood the ai_events log.
        if not log_no_setup:
            return ScanResult(candles=candles)
        # Log only fields the active strategy cares about — do not dump EMA/RSI/MACD
        # onto ICT / CE no-setup events (those series are still computed for ema_cross).
        indicators = _no_setup_indicators(
            strategy, atr14, adx14, htf_trend, ema9, ema21, rsi14, macd_hist,
        )
        if indicators is None:
            return ScanResult(candles=candles)
        rationale = no_setup_rationale(
            symbol, timeframe, indicators, strategy=strategy,
        )
        print(f"[{symbol}] no-signal analysis: {rationale}")
        return _reject(
            symbol, cfg, timeframe=timeframe, report_kind="no_setup",
            event_kind="no_setup", rationale=rationale, indicators=indicators,
            candles=candles, session=session,
        )

    tp1, tp2, tp3 = setup.resolved_take_profits()
    print(f"[{symbol}] candidate {setup.direction}: entry={setup.entry} "
          f"SL={setup.stop_loss} TP1={tp1} TP2={tp2} TP3={tp3}")

    if already_signaled(setup, cfg, timeframe=timeframe, session=session,
                        recent_signals=recent_signals,
                        open_symbols=open_symbols):
        print(f"[{symbol}] open or recent duplicate setup, skipping")
        return ScanResult(candles=candles)

    rag_block = retrieve_context(
        setup,
        strategy=strategy,
        timeframe=timeframe,
        supabase_url=cfg.supabase_url,
        service_key=cfg.supabase_service_key,
        llm=llm,
        session=session,
    )
    confirmation = confirm_setup(
        setup, llm, strategy=strategy, timeframe=timeframe,
        session_context=describe_market_session(),
        rag_block=rag_block or None,
    )
    if confirmation.verdict != "confirm":
        print(f"[{symbol}] rejected by LLM: {confirmation.rationale}")
        # Record the counterfactual before discarding it — this is the only
        # point at which a rejected setup's outcome can still be observed.
        _save_shadow(setup, confirmation, cfg,
                     timeframe=timeframe, session=session)
        return _reject(
            symbol, cfg, timeframe=timeframe, report_kind="rejected",
            event_kind="reject", rationale=confirmation.rationale,
            indicators=setup.indicators, candles=candles, setup=setup,
            confidence=confirmation.confidence, session=session,
        )

    if confirmation.confidence < min_store_confidence:
        rationale = (
            f"Confidence {confirmation.confidence} below store threshold "
            f"{min_store_confidence}: {confirmation.rationale}"
        )
        print(f"[{symbol}] confirm below store threshold "
              f"({confirmation.confidence} < {min_store_confidence})")
        return _reject(
            symbol, cfg, timeframe=timeframe, report_kind="rejected",
            event_kind="reject", rationale=rationale,
            indicators=setup.indicators, candles=candles, setup=setup,
            confidence=confirmation.confidence, session=session,
        )

    signal = make_signal(setup, confirmation, [], timeframe=timeframe)
    signal = attach_chart(
        signal, candles,
        supabase_url=cfg.supabase_url, service_key=cfg.supabase_service_key,
        session=session,
    )
    try:
        with_retry(lambda: save_signal(
            signal, cfg.supabase_url, cfg.supabase_service_key, session=session,
        ))
    except Exception as exc:
        print(f"[{symbol}] failed to store signal ({type(exc).__name__}), discarding")
        _log_ai_event(
            "reject",
            symbol,
            cfg,
            timeframe=timeframe,
            rationale=f"Confirm succeeded but storage failed: {type(exc).__name__}",
            indicators=signal.indicators,
            headlines=signal.news_headlines,
            direction=signal.direction,
            entry=signal.entry,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            confidence=signal.confidence,
            session=session,
        )
        return ScanResult(candles=candles)
    _log_ai_event(
        "confirm",
        symbol,
        cfg,
        timeframe=timeframe,
        rationale=signal.rationale,
        indicators=signal.indicators,
        headlines=signal.news_headlines,
        direction=signal.direction,
        entry=signal.entry,
        stop_loss=signal.stop_loss,
        take_profit=signal.take_profit,
        confidence=signal.confidence,
        session=session,
    )
    print(f"[{symbol}] CONFIRMED {signal.direction.upper()} "
          f"(confidence {signal.confidence}): {signal.rationale}")
    return ScanResult(signal=signal, candles=candles)


def _debate_headlines(symbol, session=None):
    """Best-effort RSS headlines for the War Room's Fundamental agent (uses the
    otherwise-dormant news client; showcase only)."""
    try:
        from signals.news_client import fetch_headlines
        return fetch_headlines(symbol, session=session)
    except Exception:
        return None


def maybe_run_debate(signal, cfg, session=None):
    """Best-effort AI War Room debate about a stored signal — a showcase that
    never affects the signal. Runs the 3 agents and saves the transcript."""
    if not cfg.supabase_url or not cfg.supabase_service_key:
        return
    try:
        keys = cfg.sealion_api_keys or (cfg.sealion_api_key,)
        llm = SeaLionClient(
            api_key=keys[datetime.now(timezone.utc).minute % len(keys)],
            model=cfg.sealion_model, base_url=cfg.sealion_base_url,
            session=session,
        )
        setup = CandidateSetup(
            signal.symbol, signal.direction, signal.entry, signal.stop_loss,
            signal.take_profit, signal.indicators,
            take_profit_2=signal.take_profit_2, take_profit_3=signal.take_profit_3,
        )
        debate = run_debate(
            setup, llm, timeframe=signal.timeframe,
            headlines=_debate_headlines(signal.symbol, session),
            calendar_block=None,
        )
        debate["signal_id"] = signal.id
        save_debate(debate, cfg.supabase_url, cfg.supabase_service_key,
                    session=session)
        print(f"[{signal.symbol}] war-room: {debate['manager_verdict']} "
              f"{debate['manager_confidence']}%")
    except Exception as exc:
        print(f"[{signal.symbol}] war-room debate skipped ({type(exc).__name__})")


def maybe_send_alert(signal, settings, cfg):
    """Telegram alert for a stored signal; never raises — a failed or
    skipped alert must not affect the rest of the run."""
    if not cfg.telegram_bot_token or not cfg.telegram_channel_id:
        return
    if signal.confidence < settings.min_alert_confidence:
        print(f"[{signal.symbol}] confidence {signal.confidence} below alert "
              f"threshold {settings.min_alert_confidence}, no alert")
        return
    try:
        with_retry(lambda: send_alert(
            signal, cfg.telegram_bot_token, cfg.telegram_channel_id,
        ))
        print(f"[{signal.symbol}] Telegram alert sent")
    except Exception as exc:
        print(f"[{signal.symbol}] Telegram alert failed "
              f"({type(exc).__name__}), continuing")


# Telegram carries confirmed signals and TP/SL outcomes only. No-signal and
# rejected scans, and per-run summaries, stay in Supabase and the logs — they
# are noise in a channel people act on. The formatters for both still exist in
# signals.telegram_client for ad-hoc use; this module deliberately never calls
# them, and tests/core/test_telegram.py asserts that.

OUTCOME_LABELS = {
    "tp_hit": "TP HIT",
    "tp1_hit": "TP1 HIT",
    "tp2_hit": "TP2 HIT",
    "tp3_hit": "TP3 HIT",
    "sl_hit": "SL HIT",
    "expired": "EXPIRED",
}


def main():
    cfg = load_config()
    # Main-thread session for Supabase reads/writes outside the scan workers.
    db_session = requests.Session()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if not try_acquire_engine_lock(
        run_id, cfg.supabase_url, cfg.supabase_service_key, session=db_session,
    ):
        print(f"Another engine run holds the lock; skipping this trigger ({run_id}).")
        return

    stored = 0
    outcomes: list[dict] = []
    candles_by_symbol: dict = {}
    session_label = "+".join(s.timeframe for s in TRADING_SESSIONS)
    try:
        settings = fetch_bot_settings(cfg.supabase_url, cfg.supabase_service_key,
                                      session=db_session)
        keys = cfg.sealion_api_keys or (cfg.sealion_api_key,)
        print(f"Using {len(keys)} SEA-LION API key(s) across "
              f"{len(settings.symbols)} symbol(s) in {len(TRADING_SESSIONS)} "
              f"session(s) ({session_label}), "
              f"swing_strategy={settings.signal_strategy}, "
              f"scalp=sr_zone, super_scalp=ict_fvg.")

        def scan_one(item):
            """(index, symbol, TradingSession, recent_events, recent_signals, open_symbols)
            -> (ScanResult | None, error | None)."""
            (index, symbol, trading_session, recent_events, recent_signals,
             open_symbols) = item
            # Symbols round-robin across keys so a full scan never concentrates
            # its LLM calls on a single key's rate limit.
            llm = SeaLionClient(
                api_key=keys[index % len(keys)],
                model=cfg.sealion_model,
                base_url=cfg.sealion_base_url,
            )
            session_strategy = (
                trading_session.strategy or settings.signal_strategy
            )
            try:
                return scan_symbol(
                    symbol, cfg, llm, strategy=session_strategy,
                    timeframe=trading_session.timeframe,
                    session=requests.Session(),
                    recent_events=recent_events, recent_signals=recent_signals,
                    open_symbols=open_symbols,
                    confluence_timeframe=trading_session.confluence_timeframe,
                    min_store_confidence=settings.min_store_confidence,
                ), None
            except Exception as exc:
                return None, exc

        workers = max(1, min(len(settings.symbols), MAX_SCAN_WORKERS))

        # Each session (scalp, swing) scans all symbols in parallel, one session
        # at a time — so a run's outcomes group by session for a clear summary.
        for trading_session in TRADING_SESSIONS:
            # One query each for the whole session's symbol list, instead of
            # every symbol hitting Supabase individually before its scan even
            # starts — collapses up to 3*len(symbols) round trips into 3.
            recent_events = _prefetch_recent_events(
                settings.symbols, trading_session.timeframe, cfg, session=db_session)
            recent_signals = _prefetch_recent_signals(
                settings.symbols, trading_session.timeframe, cfg, session=db_session)
            open_symbols = _prefetch_open_symbols(
                settings.symbols, trading_session.timeframe, cfg, session=db_session)
            tasks = [
                (i, symbol, trading_session, recent_events, recent_signals, open_symbols)
                for i, symbol in enumerate(settings.symbols)
            ]
            with ThreadPoolExecutor(max_workers=workers) as pool:
                results = list(pool.map(scan_one, tasks))

            # Alerts go out from the main thread, in symbol order, after the
            # session's scans finish.
            for symbol, (result, error) in zip(settings.symbols, results):
                if error is not None:
                    print(f"[{symbol}] unexpected error, skipping: "
                          f"{type(error).__name__}: {error}")
                    outcomes.append({
                        "symbol": symbol,
                        "timeframe": trading_session.timeframe,
                        "status": "ERROR",
                        "extra": f"{type(error).__name__}",
                    })
                    continue
                if result.candles:
                    candles_by_symbol[(symbol, trading_session.timeframe)] = result.candles
                if result.signal is not None:
                    stored += 1
                    maybe_send_alert(result.signal, settings, cfg)
                    maybe_run_debate(result.signal, cfg, session=db_session)
                    outcomes.append({
                        "symbol": symbol,
                        "timeframe": trading_session.timeframe,
                        "status": "CONFIRMED",
                        "extra": f"{result.signal.direction.upper()} {result.signal.confidence}%",
                    })
                elif result.no_signal is not None:
                    # No Telegram for no-setup / rejected — only confirmed
                    # signals and SL/TP hits get pushed.
                    if result.no_signal.kind == "rejected":
                        outcomes.append({
                            "symbol": symbol,
                            "timeframe": trading_session.timeframe,
                            "status": "REJECTED",
                            "extra": (result.no_signal.rationale or "")[:140],
                        })
                    else:
                        outcomes.append({
                            "symbol": symbol,
                            "timeframe": trading_session.timeframe,
                            "status": "NO SIGNAL",
                            "extra": (result.no_signal.rationale or "")[:140],
                        })
                else:
                    outcomes.append({
                        "symbol": symbol,
                        "timeframe": trading_session.timeframe,
                        "status": "SKIPPED",
                        "extra": "No change (dedup) or missing indicators/data",
                    })

        # After scanning both sessions, settle open signals whose TP or SL has
        # been hit and expire stale ones (per-session window), reusing this
        # run's candles where they already cover a signal's life.
        for row, outcome in track_open_signals(cfg, prefetched=candles_by_symbol,
                                               session=db_session):
            entry = {
                "symbol": row["symbol"],
                "status": OUTCOME_LABELS.get(outcome, outcome.upper()),
                "extra": f"{row['direction'].upper()} closed",
            }
            if row.get("timeframe"):
                entry["timeframe"] = row["timeframe"]
            outcomes.append(entry)
        try:
            with_retry(lambda: save_engine_run(
                {
                    "id": str(uuid.uuid4()),
                    "run_id": run_id,
                    "timeframe": session_label,
                    "stored_count": stored,
                    "outcomes": outcomes,
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                },
                cfg.supabase_url,
                cfg.supabase_service_key,
                session=db_session,
            ))
        except Exception as exc:
            print(f"Failed to store engine run heartbeat ({type(exc).__name__}), continuing")
        # Run summary stays in Supabase / logs only — not pushed to Telegram.
        print(f"Done. {stored} signal(s) stored in Supabase.")
    finally:
        release_engine_lock(
            run_id, cfg.supabase_url, cfg.supabase_service_key, session=db_session,
        )


if __name__ == "__main__":
    main()
