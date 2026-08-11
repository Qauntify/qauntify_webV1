"""Recency/dedup throttles and retry helper shared across the scan pipeline."""
import time
from datetime import datetime, timedelta, timezone

from signals.models import TIMEFRAME_MINUTES
from signals.persistence.events import (
    latest_ai_event_time,
    latest_ai_event_times_since,
)
from signals.persistence.signals import (
    latest_signal,
    latest_signals_since,
    open_symbols_for_timeframe,
)

RETRY_DELAY = 2.0

# Sentinel: prefetch failed — callers must fail closed (skip / block).
PREFETCH_UNAVAILABLE = object()

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
# Super Scalp runs hot: re-check 5m sooner so a no_setup does not blank the
# whole next bar window before a sweep reclaim can print.
EVAL_THROTTLE_BY_TIMEFRAME = {"5m": 0.3}


def _eval_throttle_fraction(timeframe: str) -> float:
    return EVAL_THROTTLE_BY_TIMEFRAME.get(timeframe, EVAL_THROTTLE_FRACTION)


def _prefetch_recent_events(symbols, timeframe, cfg, session=None):
    """One batched query replacing what would otherwise be one
    latest_ai_event_time lookup per symbol in `symbols`. Returns
    PREFETCH_UNAVAILABLE on failure so callers fail closed."""
    minutes = TIMEFRAME_MINUTES.get(timeframe, TIMEFRAME_MINUTES["1h"])
    since = (datetime.now(timezone.utc)
             - timedelta(minutes=minutes * _eval_throttle_fraction(timeframe))).isoformat()
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
    threshold = timedelta(minutes=minutes * _eval_throttle_fraction(timeframe))
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
