"""Per-symbol scan: detect a setup, confirm via LLM, gate, store."""
import os
import random
import uuid
from dataclasses import replace
from datetime import datetime, timezone

from signals.chart.pipeline import attach_chart
from signals.clients.market import is_gold_symbol, setup_stop_risk_ok
from signals.persistence.events import save_ai_event
from signals.persistence.mt5 import fetch_mt5_last_tick
from signals.persistence.signals import save_signal
from signals.pipeline.composer import confirm_setup, no_setup_rationale
from signals.pipeline.dedup import _recently_evaluated, already_signaled, with_retry
from signals.pipeline.market_data import (
    _latest_indicators,
    _load_market_data,
    _snap_gold_setup_to_live,
    resolve_gold_live_price,
)
from signals.analysis.session_clock import describe_market_session
from signals.models import (
    DEFAULT_SIGNAL_STRATEGY,
    Confirmation,
    NoSignalReport,
    ScanResult,
    make_signal,
)
from signals.rag import retrieve_context
from signals.strategies import detect_setup


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

# Per-strategy floor on top of admin min_store_confidence. cloud_mss is live
# on 15m despite measured-weak expectancy — require a stronger LLM confirm
# until forward net R earns a lower bar.
STRATEGY_MIN_STORE_CONFIDENCE = {
    "cloud_mss": 70,
}


def effective_min_store_confidence(strategy: str, admin_floor: int) -> int:
    return max(int(admin_floor or 0), STRATEGY_MIN_STORE_CONFIDENCE.get(strategy, 0))


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
    if strategy in ("ict_smc", "ict_fvg", "sr_zone", "cloud_mss"):
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

    if is_gold_symbol(symbol):
        try:
            live, live_source = resolve_gold_live_price(
                cfg, session=session, require_mt5=True,
            )
            tick = fetch_mt5_last_tick(
                "XAUUSD", cfg.supabase_url, cfg.supabase_service_key,
                session=session,
            )
            pre_live_setup = setup
            setup, _live_note = _snap_gold_setup_to_live(
                setup, live, timeframe, source=live_source,
            )
            if setup is None:
                print(f"[{symbol}] live market check failed: {_live_note}")
                return _reject(
                    symbol, cfg, timeframe=timeframe, report_kind="rejected",
                    event_kind="reject", rationale=_live_note,
                    indicators=pre_live_setup.indicators,
                    candles=candles, setup=pre_live_setup, session=session,
                )
            if tick:
                ind = dict(setup.indicators)
                ind["mt5_bid"] = tick.get("bid")
                ind["mt5_ask"] = tick.get("ask")
                ind["mt5_mid"] = tick.get("mid") or live
                setup = replace(setup, indicators=ind)
            if setup.entry != pre_live_setup.entry:
                print(f"[{symbol}] snapped entry {pre_live_setup.entry:.2f} "
                      f"-> live {live_source} {setup.entry:.2f}")
            else:
                print(f"[{symbol}] live check ok via {live_source} @ {live:.2f}")
        except Exception as exc:
            print(f"[{symbol}] live gold gate blocked publish: {exc}")
            return _reject(
                symbol, cfg, timeframe=timeframe, report_kind="rejected",
                event_kind="reject",
                rationale=str(exc),
                indicators=setup.indicators, candles=candles, setup=setup,
                session=session,
            )

    ok, stop_note = setup_stop_risk_ok(setup.entry, setup.stop_loss)
    if not ok:
        print(f"[{symbol}] {stop_note}")
        return _reject(
            symbol, cfg, timeframe=timeframe, report_kind="rejected",
            event_kind="reject", rationale=stop_note,
            indicators=setup.indicators, candles=candles, setup=setup,
            confidence=confirmation.confidence, session=session,
        )

    # Re-check after LLM / gold snap — a concurrent run may have stored first.
    if already_signaled(setup, cfg, timeframe=timeframe, session=session):
        print(f"[{symbol}] lost race to concurrent store, skipping publish")
        return ScanResult(candles=candles)

    signal = make_signal(setup, confirmation, [], timeframe=timeframe)
    signal = attach_chart(
        signal, candles,
        supabase_url=cfg.supabase_url, service_key=cfg.supabase_service_key,
        session=session, h1_candles=h1_candles,
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
