"""On-demand pipeline: scan symbols, confirm setups via LLM, store signals.

Usage: python -m signals.run
"""
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import requests

from signals.binance_client import fetch_candles
from signals.composer import confirm_setup, explain_no_setup
from signals.config import load_config
from signals.indicators import atr, ema, macd_histogram, rsi
from signals.llm_client import SeaLionClient
from signals.models import DEFAULT_SIGNAL_STRATEGY, NoSignalReport, ScanResult, make_signal
from signals.news_client import fetch_feed_titles, fetch_headlines, filter_headlines
from signals.outcome_tracker import track_open_signals
from signals.strategies import detect_setup
from signals.storage import fetch_bot_settings, latest_signal, save_ai_event, save_engine_run, save_signal
from signals.telegram_client import send_alert, send_no_signal_alert, send_run_summary

RETRY_DELAY = 2.0

# Scans are I/O-bound (Binance, SEA-LION, Supabase), so symbols run in
# parallel. Each worker gets its own requests.Session and LLM client —
# neither is thread-safe to share.
MAX_SCAN_WORKERS = 4

# The detector flags a crossover on any of the last CROSS_LOOKBACK (3) hourly
# bars, so runs closer together than that would re-store the same setup.
# Skip a candidate when the same symbol+direction was stored this recently.
DEDUP_WINDOW = timedelta(hours=3)


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


def already_signaled(setup, cfg, session=None):
    """True when the newest stored signal for this symbol duplicates the
    candidate (same direction, within DEDUP_WINDOW). On any lookup failure
    return False — better a duplicate than a missed signal."""
    try:
        row = latest_signal(setup.symbol, cfg.supabase_url,
                            cfg.supabase_service_key, session=session)
    except Exception as exc:
        print(f"[{setup.symbol}] dedup check failed "
              f"({type(exc).__name__}), proceeding")
        return False
    if row is None or row["direction"] != setup.direction:
        return False
    stored_at = datetime.fromisoformat(row["created_at"])
    return datetime.now(timezone.utc) - stored_at < DEDUP_WINDOW


def _latest_indicators(ema9, ema21, rsi14, macd_hist):
    if None in (ema9[-1], ema21[-1], rsi14[-1], macd_hist[-1]):
        return None
    return {
        "ema9": ema9[-1],
        "ema21": ema21[-1],
        "rsi": rsi14[-1],
        "macd_hist": macd_hist[-1],
    }


def _fetch_headlines_safe(symbol, session=None):
    try:
        return with_retry(lambda: fetch_headlines(symbol, session=session))
    except Exception as exc:
        print(f"[{symbol}] news unavailable ({type(exc).__name__}), proceeding without")
        return []


def _fetch_feed_titles_safe(session=None):
    """All feed titles, fetched once per run; [] when every feed is down."""
    try:
        return with_retry(lambda: fetch_feed_titles(session=session))
    except Exception as exc:
        print(f"news feeds unavailable ({type(exc).__name__}), proceeding without")
        return []


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


def scan_symbol(symbol, cfg, llm, *, strategy=DEFAULT_SIGNAL_STRATEGY,
                feed_titles=None, session=None):
    """Scan one symbol; return a ScanResult with a stored signal or a no-signal report.

    `feed_titles` holds this run's already-fetched RSS titles; when None the
    symbol's headlines are fetched directly (single-symbol / legacy use).
    """
    try:
        candles = with_retry(
            lambda: fetch_candles(symbol, cfg.timeframe, cfg.candle_limit,
                                  session=session)
        )
    except Exception as exc:
        print(f"[{symbol}] market data unavailable, skipping: {exc}")
        return ScanResult()

    # Binance returns the current, still-forming candle last — drop it so
    # indicators and entry price are computed on closed bars only.
    candles = candles[:-1]

    def headlines_for_symbol():
        if feed_titles is not None:
            return filter_headlines(feed_titles, symbol)
        return _fetch_headlines_safe(symbol, session=session)

    closes = [c.close for c in candles]
    highs = [c.high for c in candles]
    lows = [c.low for c in candles]
    ema9 = ema(closes, 9)
    ema21 = ema(closes, 21)
    rsi14 = rsi(closes, 14)
    macd_hist = macd_histogram(closes)
    atr14 = atr(highs, lows, closes, 14)

    setup = detect_setup(
        strategy, symbol, candles, ema9, ema21, rsi14, macd_hist, atr14,
    )
    if setup is None:
        print(f"[{symbol}] no setup found ({strategy})")
        indicators = _latest_indicators(ema9, ema21, rsi14, macd_hist)
        if strategy == "ict_smc":
            if atr14[-1] is None:
                return ScanResult(candles=candles)
            indicators = indicators or {}
            indicators = {
                **indicators,
                "strategy": "ict_smc",
                "atr": atr14[-1],
            }
        elif indicators is None:
            return ScanResult(candles=candles)
        headlines = headlines_for_symbol()
        rationale = explain_no_setup(
            symbol, cfg.timeframe, indicators, headlines, llm,
            strategy=strategy,
        )
        _log_ai_event(
            "no_setup",
            symbol,
            cfg,
            timeframe=cfg.timeframe,
            rationale=rationale,
            indicators=indicators,
            headlines=headlines,
            session=session,
        )
        print(f"[{symbol}] no-signal analysis: {rationale}")
        return ScanResult(no_signal=NoSignalReport(
            symbol=symbol,
            timeframe=cfg.timeframe,
            kind="no_setup",
            rationale=rationale,
            indicators=indicators,
        ), candles=candles)

    print(f"[{symbol}] candidate {setup.direction}: entry={setup.entry} "
          f"SL={setup.stop_loss} TP={setup.take_profit}")

    if already_signaled(setup, cfg, session=session):
        print(f"[{symbol}] same setup already stored recently, skipping")
        return ScanResult(candles=candles)

    headlines = headlines_for_symbol()
    confirmation = confirm_setup(setup, headlines, llm, strategy=strategy)
    if confirmation.verdict != "confirm":
        _log_ai_event(
            "reject",
            symbol,
            cfg,
            timeframe=cfg.timeframe,
            rationale=confirmation.rationale,
            indicators=setup.indicators,
            headlines=headlines,
            direction=setup.direction,
            entry=setup.entry,
            stop_loss=setup.stop_loss,
            take_profit=setup.take_profit,
            confidence=confirmation.confidence,
            session=session,
        )
        print(f"[{symbol}] rejected by LLM: {confirmation.rationale}")
        return ScanResult(no_signal=NoSignalReport(
            symbol=symbol,
            timeframe=cfg.timeframe,
            kind="rejected",
            rationale=confirmation.rationale,
            indicators=setup.indicators,
            direction=setup.direction,
            entry=setup.entry,
            stop_loss=setup.stop_loss,
            take_profit=setup.take_profit,
            confidence=confirmation.confidence,
        ), candles=candles)

    signal = make_signal(setup, confirmation, headlines, timeframe=cfg.timeframe)
    try:
        with_retry(lambda: save_signal(
            signal, cfg.supabase_url, cfg.supabase_service_key, session=session,
        ))
    except Exception as exc:
        print(f"[{symbol}] failed to store signal ({type(exc).__name__}), discarding")
        return ScanResult(candles=candles)
    _log_ai_event(
        "confirm",
        symbol,
        cfg,
        timeframe=cfg.timeframe,
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


def maybe_send_alert(signal, settings, cfg):
    """Telegram alert for a stored signal; never raises — a failed or
    skipped alert must not affect the rest of the run."""
    if not cfg.telegram_bot_token or not cfg.telegram_chat_id:
        return
    if signal.confidence < settings.min_alert_confidence:
        print(f"[{signal.symbol}] confidence {signal.confidence} below alert "
              f"threshold {settings.min_alert_confidence}, no alert")
        return
    try:
        with_retry(lambda: send_alert(
            signal, cfg.telegram_bot_token, cfg.telegram_chat_id,
        ))
        print(f"[{signal.symbol}] Telegram alert sent")
    except Exception as exc:
        print(f"[{signal.symbol}] Telegram alert failed "
              f"({type(exc).__name__}), continuing")


def maybe_send_no_signal_alert(report, cfg):
    """Telegram alert explaining why no signal was stored; never raises."""
    if not cfg.telegram_bot_token or not cfg.telegram_chat_id:
        return
    try:
        with_retry(lambda: send_no_signal_alert(
            report, cfg.telegram_bot_token, cfg.telegram_chat_id,
        ))
        print(f"[{report.symbol}] Telegram no-signal alert sent")
    except Exception as exc:
        print(f"[{report.symbol}] Telegram no-signal alert failed "
              f"({type(exc).__name__}), continuing")


def maybe_send_run_summary(run_id: str, timeframe: str, outcomes: list[dict], cfg) -> None:
    """Telegram per-run summary; never raises."""
    if not cfg.telegram_bot_token or not cfg.telegram_chat_id:
        return
    try:
        with_retry(lambda: send_run_summary(
            run_id,
            timeframe,
            outcomes,
            cfg.telegram_bot_token,
            cfg.telegram_chat_id,
        ))
        print("Telegram run summary sent")
    except Exception as exc:
        print(f"Telegram run summary failed ({type(exc).__name__}), continuing")


OUTCOME_LABELS = {"tp_hit": "TP HIT", "sl_hit": "SL HIT", "expired": "EXPIRED"}


def main():
    cfg = load_config()
    # Main-thread session for Supabase reads/writes outside the scan workers.
    db_session = requests.Session()
    settings = fetch_bot_settings(cfg.supabase_url, cfg.supabase_service_key,
                                  session=db_session)
    keys = cfg.sealion_api_keys or (cfg.sealion_api_key,)
    print(f"Using {len(keys)} SEA-LION API key(s) across "
          f"{len(settings.symbols)} symbol(s), "
          f"strategy={settings.signal_strategy}.")
    # RSS feeds change slower than a run: fetch them once, filter per symbol.
    feed_titles = _fetch_feed_titles_safe(session=requests.Session())

    def scan_one(item):
        """(index, symbol) -> (ScanResult | None, error | None)."""
        index, symbol = item
        # Symbols round-robin across keys so a full scan never concentrates
        # its LLM calls on a single key's rate limit.
        llm = SeaLionClient(
            api_key=keys[index % len(keys)],
            model=cfg.sealion_model,
            base_url=cfg.sealion_base_url,
        )
        try:
            return scan_symbol(
                symbol, cfg, llm, strategy=settings.signal_strategy,
                feed_titles=feed_titles, session=requests.Session(),
            ), None
        except Exception as exc:
            return None, exc

    workers = max(1, min(len(settings.symbols), MAX_SCAN_WORKERS))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(scan_one, enumerate(settings.symbols)))

    stored = 0
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    outcomes: list[dict] = []
    candles_by_symbol: dict = {}
    # Alerts go out from the main thread, in symbol order, after all scans.
    for symbol, (result, error) in zip(settings.symbols, results):
        if error is not None:
            print(f"[{symbol}] unexpected error, skipping: "
                  f"{type(error).__name__}: {error}")
            outcomes.append({
                "symbol": symbol,
                "status": "ERROR",
                "extra": f"{type(error).__name__}",
            })
            continue
        if result.candles:
            candles_by_symbol[symbol] = result.candles
        if result.signal is not None:
            stored += 1
            maybe_send_alert(result.signal, settings, cfg)
            outcomes.append({
                "symbol": symbol,
                "status": "CONFIRMED",
                "extra": f"{result.signal.direction.upper()} {result.signal.confidence}%",
            })
        elif result.no_signal is not None:
            maybe_send_no_signal_alert(result.no_signal, cfg)
            if result.no_signal.kind == "rejected":
                outcomes.append({
                    "symbol": symbol,
                    "status": "REJECTED",
                    "extra": (result.no_signal.rationale or "")[:140],
                })
            else:
                outcomes.append({
                    "symbol": symbol,
                    "status": "NO SIGNAL",
                    "extra": (result.no_signal.rationale or "")[:140],
                })
        else:
            outcomes.append({
                "symbol": symbol,
                "status": "SKIPPED",
                "extra": "No change (dedup) or missing indicators/data",
            })
    # After scanning, settle open signals whose TP or SL has been hit and
    # expire stale ones, reusing this run's candles where they suffice.
    for row, outcome in track_open_signals(cfg, prefetched=candles_by_symbol,
                                           session=db_session):
        outcomes.append({
            "symbol": row["symbol"],
            "status": OUTCOME_LABELS.get(outcome, outcome.upper()),
            "extra": f"{row['direction'].upper()} closed",
        })
    try:
        with_retry(lambda: save_engine_run(
            {
                "id": str(uuid.uuid4()),
                "run_id": run_id,
                "timeframe": cfg.timeframe,
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
    maybe_send_run_summary(run_id, cfg.timeframe, outcomes, cfg)
    print(f"Done. {stored} signal(s) stored in Supabase.")


if __name__ == "__main__":
    main()
