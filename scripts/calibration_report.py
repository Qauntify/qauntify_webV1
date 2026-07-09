#!/usr/bin/env python3
"""Report win rate / expectancy of closed signals, grouped by strategy,
symbol, timeframe, and confidence bucket.

Closes the loop between outcome_tracker's recorded results and the
parameters that produced them — run this after enough signals have closed
to check a strategy or threshold change against real history instead of
guessing.

Usage:
  python scripts/calibration_report.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from signals.calibration import calibration_report
from signals.config import load_config
from signals.storage import list_closed_signals


def _fmt_win_rate(win_rate) -> str:
    return f"{win_rate * 100:.0f}%" if win_rate is not None else "n/a"


def _fmt_avg_r(avg_r) -> str:
    return f"{avg_r:+.2f}R" if avg_r is not None else "n/a"


def _print_row(label: str, stats: dict) -> None:
    print(
        f"  {label:<20} n={stats['count']:<4} "
        f"win_rate={_fmt_win_rate(stats['win_rate']):<6} "
        f"avg_r={_fmt_avg_r(stats['avg_r']):<8} "
        f"(wins={stats['wins']} losses={stats['losses']} expired={stats['expired']})"
    )


def _print_group(title: str, stats_by_key: dict) -> None:
    print(f"\n{title}")
    for key in sorted(stats_by_key):
        _print_row(key, stats_by_key[key])


def main() -> int:
    cfg = load_config()
    rows = list_closed_signals(cfg.supabase_url, cfg.supabase_service_key)
    if not rows:
        print("No closed signals yet.")
        return 0

    report = calibration_report(rows)
    print("Overall")
    _print_row("all", report["overall"])
    _print_group("By strategy", report["by_strategy"])
    _print_group("By symbol", report["by_symbol"])
    _print_group("By timeframe", report["by_timeframe"])
    _print_group("By confidence bucket", report["by_confidence"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
