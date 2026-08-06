"""Wall-clock bar-close helpers for the live scanner.

Detectors + AI run on *closed* candles. These helpers decide which trading
sessions are due right after a 5m / 15m / 1h bucket rolls over, and dedupe so
each closed bar fires at most once.
"""
from __future__ import annotations

from signals.market_client import INTERVAL_MINUTES
from signals.models import TradingSession

# How long after a bar boundary we still consider it a "fresh close".
DEFAULT_CLOSE_WINDOW_MS = 45_000


def timeframe_width_ms(timeframe: str) -> int:
    minutes = INTERVAL_MINUTES.get(timeframe)
    if minutes is None:
        raise ValueError(f"unsupported timeframe: {timeframe}")
    return minutes * 60_000


def closed_bar_open_ms(now_ms: int, timeframe: str) -> int:
    """Open time (ms) of the most recently *fully closed* bar."""
    width = timeframe_width_ms(timeframe)
    current_open = (int(now_ms) // width) * width
    return current_open - width


def just_closed(now_ms: int, timeframe: str, *,
                window_ms: int = DEFAULT_CLOSE_WINDOW_MS) -> bool:
    """True when wall clock is within `window_ms` after a bar boundary."""
    width = timeframe_width_ms(timeframe)
    elapsed = int(now_ms) % width
    return 0 <= elapsed < int(window_ms)


def sessions_due(
    now_ms: int,
    sessions: tuple[TradingSession, ...] | list[TradingSession],
    last_fired: dict[str, int],
    *,
    window_ms: int = DEFAULT_CLOSE_WINDOW_MS,
) -> list[TradingSession]:
    """Sessions whose bar just closed and have not been fired for that bar.

    Mutates `last_fired` in place: key = session.name, value = closed bar
    open_ms that was claimed.
    """
    due: list[TradingSession] = []
    for session in sessions:
        if not just_closed(now_ms, session.timeframe, window_ms=window_ms):
            continue
        bar_open = closed_bar_open_ms(now_ms, session.timeframe)
        if last_fired.get(session.name) == bar_open:
            continue
        last_fired[session.name] = bar_open
        due.append(session)
    return due
