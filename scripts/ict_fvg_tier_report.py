"""Splits ict_fvg's long-history results (scripts/ict_fvg_history_report.py)
by confirmation tier -- does a real edge exist in a SUBSET of the detector's
current logic, even though the pooled average
(docs/ict-fvg-backtest-results.md) doesn't show one?

ict_fvg fires on three tiers of decreasing structural confirmation:
  choch_fvg      -- full sweep -> CHoCH -> FVG -> retest (the "textbook" entry)
  choch          -- sweep -> CHoCH, no FVG retest yet
  sweep_reclaim  -- bare sweep + reclaim, no CHoCH (the volume fallback)

This is a diagnostic, not a parameter search: the tiers are the detector's
own pre-existing, theory-grounded categories (signals/strategies/ict_fvg/
detector.py's `structure` indicator), not thresholds picked to make a number
look better. Same data, gates, and cost model as ict_fvg_history_report.py --
see that script and docs/ict-fvg-backtest-results.md for the harness details.

Usage: .venv/bin/python -m scripts.ict_fvg_tier_report
"""
import statistics
from collections import defaultdict
from datetime import datetime, timezone

import requests

from signals.analysis.backtest import htf_trend_series, net_r_multiples, simulate_scaled
from signals.analysis.history import load_history
from signals.analysis.indicators import atr
from signals.analysis.r_model import scaled_r
from signals.analysis.session_clock import scalp_session_active
from signals.pipeline.scan import _htf_opposes_setup
from signals.strategies.ict_fvg.detector import detect_setup

SYMBOLS = ("BTCUSD", "ETHUSD")
TIMEFRAME = "5m"
CONFLUENCE_TIMEFRAME = "15m"
CONFLUENCE_MINUTES = 15
WINDOW = 200
MAX_HOLD = 2000


def _super_scalp_gate(candle, setup) -> bool:
    """Mirrors scan.py's two hard gates -- see ict_fvg_history_report.py."""
    now = datetime.fromtimestamp(candle.open_time / 1000, tz=timezone.utc)
    if not scalp_session_active(now):
        return False
    return not _htf_opposes_setup(setup.direction, setup.indicators.get("htf_trend"))


def main():
    session = requests.Session()
    tiers = defaultdict(lambda: {"gross": [], "entries": [], "stops": []})
    total_trades = 0

    for symbol in SYMBOLS:
        candles = load_history(symbol, TIMEFRAME, session=session)
        htf_candles = load_history(symbol, CONFLUENCE_TIMEFRAME, session=session)
        highs = [c.high for c in candles]
        lows = [c.low for c in candles]
        closes = [c.close for c in candles]
        atr14 = atr(highs, lows, closes, 14)
        trends = htf_trend_series(candles, htf_candles, CONFLUENCE_MINUTES)

        n = len(candles)
        i = WINDOW
        while i < n - 1:
            lo = i - WINDOW + 1
            setup = detect_setup(symbol, candles[lo:i + 1], atr14[lo:i + 1],
                                 htf_trend=trends[i])
            if setup is None or not _super_scalp_gate(candles[i], setup):
                i += 1
                continue
            tps = list(setup.resolved_take_profits())
            reached, stopped, bars = simulate_scaled(
                setup.direction, setup.entry, setup.stop_loss, tps,
                candles[i + 1:i + 1 + MAX_HOLD],
            )
            gross = scaled_r(setup.direction, setup.entry, setup.stop_loss,
                             tps, reached, stopped)
            structure = setup.indicators.get("structure", "unknown")
            tier = structure.replace("bullish_", "").replace("bearish_", "")
            tiers[tier]["gross"].append(gross)
            tiers[tier]["entries"].append(setup.entry)
            tiers[tier]["stops"].append(setup.stop_loss)
            total_trades += 1
            i = i + 1 + max(bars, 1)

    print("ict_fvg long-history trades split by confirmation tier -- does a "
          "real edge exist in a subset of the detector's own logic?\n")
    print(f"{'tier':16} {'n':>7} {'share':>7} {'gross/tr':>9} {'t(gross)':>9} "
          f"{'net/tr':>9} {'t(net)':>9}")
    print("-" * 72)
    # Strongest confirmation first (matches the doc table).
    order = ["choch_fvg", "choch", "sweep_reclaim"]
    for tier in order:
        d = tiers.get(tier)
        if not d or len(d["gross"]) < 2:
            continue
        n = len(d["gross"])
        net = net_r_multiples("BTCUSD", d["gross"], d["entries"], d["stops"])
        mean_g = statistics.mean(d["gross"])
        t_g = mean_g / (statistics.stdev(d["gross"]) / n ** 0.5)
        mean_n = statistics.mean(net)
        t_n = mean_n / (statistics.stdev(net) / n ** 0.5)
        share = n / total_trades * 100
        print(f"{tier:16} {n:7d} {share:6.1f}% {mean_g:+8.3f}R {t_g:+8.2f} "
              f"{mean_n:+8.3f}R {t_n:+8.2f}")


if __name__ == "__main__":
    main()
