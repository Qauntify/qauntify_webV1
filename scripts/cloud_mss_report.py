"""cloud_mss over the full verified Binance history.

15m primary with 1h for the cloud. Provenance for the archives is established
by scripts/history_provenance.py — SHA256 against Binance's published digests
plus known market events located at their correct dates.

Scored under the corrected fixed-stop R model (docs/r-model-correction.md):
one third booked at each of TP1/TP2/TP3, the published stop never moves, so an
unbooked remainder loses its full share when the stop is hit.

Usage: .venv/bin/python -m scripts.cloud_mss_report
"""
import statistics

import requests

from signals.analysis.backtest import backtest_windowed
from signals.analysis.history import load_history
from signals.analysis.indicators import atr
from signals.strategies.cloud_mss import detect_setup

SYMBOLS = ("BTCUSD", "ETHUSD")
PRIMARY = "15m"
HTF = "1h"
HTF_MINUTES = 60
# Matches _candle_limit_for("cloud_mss", cfg) minus the forming bar, so the
# replay sees exactly what a live scan sees.
WINDOW = 259
MAX_HOLD = 2000


def main():
    session = requests.Session()
    pooled = []
    print("cloud_mss over verified Binance history. 15m primary, 1h cloud.")
    print("Fixed stop as published; net subtracts r_model round-trip costs.\n")
    print(f"{'symbol':8} {'years':>6} {'bars':>8} {'trades':>7} {'tp1%':>6} "
          f"{'gross':>8} {'net':>8} {'total':>9}")
    print("-" * 68)

    for symbol in SYMBOLS:
        candles = load_history(symbol, PRIMARY, session=session)
        htf = load_history(symbol, HTF, session=session)
        atr14 = atr([c.high for c in candles], [c.low for c in candles],
                    [c.close for c in candles], 14)
        out = backtest_windowed(
            detect_setup, symbol, candles, atr14, [None] * len(candles),
            window=WINDOW, max_hold=MAX_HOLD,
            htf_candles=htf, htf_minutes=HTF_MINUTES,
        )
        gross, net = out["gross"], out["net"]
        trades = len(gross)
        pooled += net
        years = ((candles[-1].open_time - candles[0].open_time)
                 / 1000 / 86400 / 365.25)
        if not trades:
            print(f"{symbol:8} {years:6.2f} {len(candles):8d} {0:7d}   no trades")
            continue
        print(f"{symbol:8} {years:6.2f} {len(candles):8d} {trades:7d} "
              f"{out['tp1_hits'] / trades * 100:5.1f}% "
              f"{statistics.mean(gross):+7.3f}R {statistics.mean(net):+7.3f}R "
              f"{sum(net):+8.1f}R")

    n = len(pooled)
    if n < 2:
        print(f"\nPOOLED n={n} — too few to summarise")
        return
    mean = statistics.mean(pooled)
    se = statistics.stdev(pooled) / (n ** 0.5)
    lo, hi = mean - 1.96 * se, mean + 1.96 * se
    verdict = ("PROFITABLE" if lo > 0 else
               "LOSING" if hi < 0 else "indistinguishable from zero")
    print("\n" + "=" * 68)
    print(f"POOLED n={n}  net={mean:+.3f}R  t={mean / se:+.2f}  "
          f"95% CI [{lo:+.3f}, {hi:+.3f}]  total={sum(pooled):+.1f}R")
    print(f"VERDICT: {verdict}")


if __name__ == "__main__":
    main()
