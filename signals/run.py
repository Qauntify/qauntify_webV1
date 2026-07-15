"""On-demand pipeline: scan symbols, confirm setups via LLM, store signals.

Usage: python -m signals.run
"""
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import requests

from signals.binance_client import fetch_candles
from signals.calendar_client import (
    calendar_block_for_symbol,
    fetch_calendar_events,
)
from signals.composer import confirm_setup, no_setup_rationale
from signals.rag import retrieve_context
from signals.config import load_config
from signals.indicators import adx, atr, ema, macd_histogram, rsi
from signals.llm_client import SeaLionClient
from signals.models import (
    DEFAULT_SIGNAL_STRATEGY,
    TIMEFRAME_MINUTES,
    TRADING_SESSIONS,
    NoSignalReport,
    ScanResult,
    make_signal,
)
from signals.news_client import fetch_feed_titles, fetch_headlines, filter_headlines
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


def _fetch_calendar_events_safe(session=None):
    """This week's economic calendar.

    Returns a list on success (may be empty). Returns None when the free
    feed is down so the AI prompt can say "unavailable" instead of
    pretending the day is quiet.
    """
    try:
        return with_retry(lambda: fetch_calendar_events(session=session))
    except Exception as exc:
        print(f"economic calendar unavailable ({type(exc).__name__}), proceeding without")
        return None


CALENDAR_UNAVAILABLE_BLOCK = (
    "Economic calendar UNAVAILABLE this run (feed error). "
    "Do not assume a quiet macro day — weigh headlines carefully and reduce "
    "confidence if the setup looks news-driven."
)

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


def scan_symbol(symbol, cfg, llm, *, strategy=DEFAULT_SIGNAL_STRATEGY,
                timeframe=None, feed_titles=None, calendar_events=None,
                session=None,
                recent_events=None, recent_signals=None,
                open_symbols=None, confluence_timeframe=None,
                min_store_confidence=0):
    """Scan one symbol on one session's timeframe; return a ScanResult with
    a stored signal or a no-signal report.

    `timeframe` selects the session (e.g. "15m" scalp, "1h" swing);
    defaults to cfg.timeframe for single-session callers. `feed_titles`
    holds this run's already-fetched RSS titles; when None the symbol's
    headlines are fetched directly (single-symbol / legacy use).
    `calendar_events` is this run's economic calendar prefetch (may be []).
    `recent_events`/`recent_signals`/`open_symbols` are this session's
    prefetched maps; when None each check falls back to its own
    per-symbol query. `confluence_timeframe`, when given, requires a
    successful HTF trend read and gates setups on agreement.
    `min_store_confidence` drops LLM confirms below the admin quality bar
    before they hit storage (not just Telegram).
    """
    timeframe = timeframe or cfg.timeframe

    if _recently_evaluated(symbol, timeframe, cfg, session=session,
                           recent_events=recent_events):
        print(f"[{symbol}] {timeframe} evaluated recently, skipping this run")
        return ScanResult()

    # CE+LWMA needs 200 M15 bars for LWMA warm-up; other strategies use cfg.
    candle_limit = max(cfg.candle_limit, 220) if strategy == "ce_lwma" else cfg.candle_limit
    try:
        candles = with_retry(
            lambda: fetch_candles(symbol, timeframe, candle_limit,
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

    def calendar_context_for_symbol():
        if calendar_events is None:
            return CALENDAR_UNAVAILABLE_BLOCK
        return calendar_block_for_symbol(calendar_events, symbol)

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
            return ScanResult(candles=candles)
    elif confluence_timeframe:
        try:
            htf_trend = _fetch_htf_trend(symbol, confluence_timeframe, cfg,
                                         session=session)
        except Exception as exc:
            print(f"[{symbol}] HTF confluence required but unavailable "
                  f"({type(exc).__name__}), skipping")
            return ScanResult(candles=candles)

    setup = detect_setup(
        strategy, symbol, candles, ema9, ema21, rsi14, macd_hist, atr14,
        adx14=adx14, htf_trend=htf_trend, h1_candles=h1_candles,
    )
    if setup is None:
        print(f"[{symbol}] no setup found ({strategy})")
        # Log only fields the active strategy cares about — do not dump EMA/RSI/MACD
        # onto ICT / CE no-setup events (those series are still computed for ema_cross).
        if strategy == "ict_smc":
            if atr14[-1] is None:
                return ScanResult(candles=candles)
            indicators = {
                "strategy": "ict_smc",
                "atr": atr14[-1],
            }
            if adx14[-1] is not None:
                indicators["adx"] = adx14[-1]
            if htf_trend is not None:
                indicators["htf_trend"] = htf_trend
        elif strategy == "ict_fvg":
            if atr14[-1] is None:
                return ScanResult(candles=candles)
            indicators = {
                "strategy": "ict_fvg",
                "atr": atr14[-1],
            }
            if htf_trend is not None:
                indicators["htf_trend"] = htf_trend
        elif strategy == "ce_lwma":
            indicators = {"strategy": "ce_lwma"}
        else:
            indicators = _latest_indicators(ema9, ema21, rsi14, macd_hist)
            if indicators is None:
                return ScanResult(candles=candles)
        headlines = headlines_for_symbol()
        rationale = no_setup_rationale(
            symbol, timeframe, indicators, strategy=strategy,
        )
        _log_ai_event(
            "no_setup",
            symbol,
            cfg,
            timeframe=timeframe,
            rationale=rationale,
            indicators=indicators,
            headlines=headlines,
            session=session,
        )
        print(f"[{symbol}] no-signal analysis: {rationale}")
        return ScanResult(no_signal=NoSignalReport(
            symbol=symbol,
            timeframe=timeframe,
            kind="no_setup",
            rationale=rationale,
            indicators=indicators,
        ), candles=candles)

    tp1, tp2, tp3 = setup.resolved_take_profits()
    print(f"[{symbol}] candidate {setup.direction}: entry={setup.entry} "
          f"SL={setup.stop_loss} TP1={tp1} TP2={tp2} TP3={tp3}")

    if already_signaled(setup, cfg, timeframe=timeframe, session=session,
                        recent_signals=recent_signals,
                        open_symbols=open_symbols):
        print(f"[{symbol}] open or recent duplicate setup, skipping")
        return ScanResult(candles=candles)

    headlines = headlines_for_symbol()
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
        setup, headlines, llm, strategy=strategy, timeframe=timeframe,
        session_context=describe_market_session(),
        calendar_block=calendar_context_for_symbol(),
        rag_block=rag_block or None,
    )
    if confirmation.verdict != "confirm":
        _log_ai_event(
            "reject",
            symbol,
            cfg,
            timeframe=timeframe,
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
            timeframe=timeframe,
            kind="rejected",
            rationale=confirmation.rationale,
            indicators=setup.indicators,
            direction=setup.direction,
            entry=setup.entry,
            stop_loss=setup.stop_loss,
            take_profit=setup.take_profit,
            confidence=confirmation.confidence,
        ), candles=candles)

    if confirmation.confidence < min_store_confidence:
        rationale = (
            f"Confidence {confirmation.confidence} below store threshold "
            f"{min_store_confidence}: {confirmation.rationale}"
        )
        _log_ai_event(
            "reject",
            symbol,
            cfg,
            timeframe=timeframe,
            rationale=rationale,
            indicators=setup.indicators,
            headlines=headlines,
            direction=setup.direction,
            entry=setup.entry,
            stop_loss=setup.stop_loss,
            take_profit=setup.take_profit,
            confidence=confirmation.confidence,
            session=session,
        )
        print(f"[{symbol}] confirm below store threshold "
              f"({confirmation.confidence} < {min_store_confidence})")
        return ScanResult(no_signal=NoSignalReport(
            symbol=symbol,
            timeframe=timeframe,
            kind="rejected",
            rationale=rationale,
            indicators=setup.indicators,
            direction=setup.direction,
            entry=setup.entry,
            stop_loss=setup.stop_loss,
            take_profit=setup.take_profit,
            confidence=confirmation.confidence,
        ), candles=candles)

    signal = make_signal(setup, confirmation, headlines, timeframe=timeframe)
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


def maybe_send_no_signal_alert(report, cfg):
    """Intentionally a no-op: no-signal / rejected scans are not pushed.
    Confirmed signals and SL/TP hits are the only Telegram alerts."""
    return


def maybe_send_run_summary(run_id: str, timeframe: str, outcomes: list[dict], cfg) -> None:
    """Intentionally a no-op: per-run summaries are logged/stored only,
    not pushed to Telegram."""
    return


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
              f"scalp=ce_lwma, super_scalp=ict_fvg.")
        # RSS feeds change slower than a run: fetch them once, filter per symbol.
        feed_titles = _fetch_feed_titles_safe(session=requests.Session())
        calendar_events = _fetch_calendar_events_safe(session=requests.Session())

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
                    feed_titles=feed_titles, calendar_events=calendar_events,
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
