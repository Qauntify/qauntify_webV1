"""Always-on bar-close scanner (OPTIONAL).

Prefer the EA → `/api/mt5/candles` path: when a 5m/15m/1h bar closes, Vercel
dispatches the GitHub engine. That needs only the MT5 EA on the VPS — no
Python process there.

Use this module only if you have a separate always-on host and want a
wall-clock backup without waiting for gold M1 pushes (crypto-only wakes).

Usage::

    python -m signals.live_scanner
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone

from signals.analysis.bar_close import sessions_due
from signals.models import TRADING_SESSIONS
from signals.run import main as run_engine

POLL_SECONDS = float(os.environ.get("LIVE_SCANNER_POLL_SECONDS", "15"))


def _now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def tick(last_fired: dict[str, int], *, now_ms: int | None = None,
         run_fn=run_engine) -> list[str]:
    """One poll cycle. Returns names of sessions that were triggered."""
    due = sessions_due(now_ms if now_ms is not None else _now_ms(),
                       TRADING_SESSIONS, last_fired)
    if not due:
        return []
    names = [s.name for s in due]
    print(f"bar-close due: {', '.join(names)}")
    run_fn(sessions=due)
    return names


def main() -> None:
    print(f"live_scanner started (poll={POLL_SECONDS}s, "
          f"sessions={[s.timeframe for s in TRADING_SESSIONS]})")
    print("NOTE: VPS/EA-only setups should rely on /api/mt5/candles dispatch "
          "instead of this process.")
    last_fired: dict[str, int] = {}
    while True:
        try:
            tick(last_fired)
        except Exception as exc:
            print(f"live_scanner tick failed ({type(exc).__name__}: {exc})")
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
