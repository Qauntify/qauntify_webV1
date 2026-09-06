"""Splits msnr's long-history results (scripts/msnr_history_report.py) by
entry mode -- does a real edge exist in a SUBSET of the detector's current
logic, even though the pooled average (docs/msnr-backtest-results.md)
doesn't show one?

msnr fires through three entry modes (signals/strategies/msnr/detector.py's
`entry_mode` indicator):
  rejection -- rejection off a fresh body zone
  rbs       -- resistance broken, retested as support
  sbr       -- support broken, retested as resistance

This is a diagnostic, not a parameter search: the modes are the detector's
own pre-existing categories, not thresholds picked to make a number look
better. Same data and gates as msnr_history_report.py -- see that script and
docs/msnr-backtest-results.md for the harness details.

Usage: .venv/bin/python -m scripts.msnr_tier_report
"""
import statistics
from collections import defaultdict

import requests

from signals.analysis.backtest import htf_trend_series, net_r_multiples, simulate_scaled
from signals.analysis.history import load_history
from signals.analysis.indicators import atr
from signals.analysis.r_model import scaled_r
from signals.strategies.msnr.detector import detect_setup

SYMBOLS = ("BTCUSD", "ETHUSD")
TIMEFRAME = "1h"
CONFLUENCE_TIMEFRAME = "4h"
CONFLUENCE_MINUTES = 240
WINDOW = 200
MAX_HOLD = 2000


def main():
    session = requests.Session()
    modes = defaultdict(lambda: {"gross": [], "entries": [], "stops": []})
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
            if setup is None:
                i += 1
                continue
            tps = list(setup.resolved_take_profits())
            reached, stopped, bars = simulate_scaled(
                setup.direction, setup.entry, setup.stop_loss, tps,
                candles[i + 1:i + 1 + MAX_HOLD],
            )
            gross = scaled_r(setup.direction, setup.entry, setup.stop_loss,
                             tps, reached, stopped)
            mode = setup.indicators.get("entry_mode", "unknown")
            modes[mode]["gross"].append(gross)
            modes[mode]["entries"].append(setup.entry)
            modes[mode]["stops"].append(setup.stop_loss)
            total_trades += 1
            i = i + 1 + max(bars, 1)

    print("msnr long-history trades split by entry mode -- does a real edge "
          "exist in a subset of the detector's own logic?\n")
    print(f"{'mode':10} {'n':>6} {'share':>7} {'gross/tr':>9} {'t(gross)':>9} "
          f"{'net/tr':>9} {'t(net)':>9}")
    print("-" * 62)
    order = ["rejection", "sbr", "rbs"]
    for mode in order:
        d = modes.get(mode)
        if not d or len(d["gross"]) < 2:
            continue
        n = len(d["gross"])
        net = net_r_multiples("BTCUSD", d["gross"], d["entries"], d["stops"])
        mean_g = statistics.mean(d["gross"])
        t_g = mean_g / (statistics.stdev(d["gross"]) / n ** 0.5)
        mean_n = statistics.mean(net)
        t_n = mean_n / (statistics.stdev(net) / n ** 0.5)
        share = n / total_trades * 100
        print(f"{mode:10} {n:6d} {share:6.1f}% {mean_g:+8.3f}R {t_g:+8.2f} "
              f"{mean_n:+8.3f}R {t_n:+8.2f}")


if __name__ == "__main__":
    main()
