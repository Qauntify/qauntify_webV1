"""orb_rvol backtested over the full verified Binance history (~8.9 years).

Same data and harness as scripts/bbma_history_report.py: SHA256-verified
monthly archives (scripts/history_provenance.py -- run that first if you have
not), replayed through backtest_windowed so a setup only counts here if it
would have fired live.

Binance lists no gold or GBP, so XAUUSD and GBPUSD are not covered here -- see
the "Extended backtest history" section of
docs/superpowers/specs/2026-07-26-orb-rvol-strategy-design.md for their
shorter, live-API-paginated check instead (signals.analysis.backtest.main
with STRATEGY_TIMEFRAMES["orb_rvol"]).

WINDOW is MIN_CANDLES (400), not the 200 bbma_history_report.py uses: the
detector's own guard clause requires 400 candles just to evaluate, so a
narrower window would silently report zero trades instead of a verdict.

Usage: .venv/bin/python -m scripts.orb_rvol_report
"""
import statistics

import requests

from signals.analysis.backtest import backtest_windowed
from signals.analysis.history import load_history
from signals.analysis.indicators import atr
from signals.strategies.orb_rvol.detector import MIN_CANDLES, detect_setup

SYMBOLS = ("BTCUSD", "ETHUSD")
TIMEFRAME = "15m"
WINDOW = MIN_CANDLES
MAX_HOLD = 2000


def main():
    session = requests.Session()
    pooled_gross, pooled_net = [], []

    print("orb_rvol over the full verified Binance history. Scale-out model: "
          "1/3 at each of TP1/TP2/TP3 (2R/4R/6R), fixed stop as published.")
    print(f"{WINDOW}-bar rolling window (matches MIN_CANDLES -- the "
          "detector's own floor). No HTF gate (orb_rvol takes none by "
          "design).\n")
    print(f"{'symbol':7} {'years':>6} {'bars':>7} {'trades':>7} {'tp1%':>6} "
          f"{'tp3%':>6} {'gross':>7} {'net':>7} {'totR':>9}")
    print("-" * 70)

    for symbol in SYMBOLS:
        candles = load_history(symbol, TIMEFRAME, session=session)
        highs = [c.high for c in candles]
        lows = [c.low for c in candles]
        closes = [c.close for c in candles]
        atr14 = atr(highs, lows, closes, 14)
        trends = [None] * len(candles)

        out = backtest_windowed(detect_setup, symbol, candles, atr14, trends,
                                window=WINDOW, max_hold=MAX_HOLD)
        gross, net = out["gross"], out["net"]
        trades = len(gross)
        pooled_gross += gross
        pooled_net += net

        years = ((candles[-1].open_time - candles[0].open_time)
                 / 1000 / 86400 / 365.25)
        if trades:
            print(f"{symbol:7} {years:6.2f} {len(candles):7d} {trades:7d} "
                  f"{out['tp1_hits'] / trades * 100:5.1f}% "
                  f"{out['tp3_hits'] / trades * 100:5.1f}% "
                  f"{statistics.mean(gross):+6.3f}R "
                  f"{statistics.mean(net):+6.3f}R "
                  f"{sum(net):+8.1f}R")
        else:
            print(f"{symbol:7} {years:6.2f} {len(candles):7d} {0:7d}   "
                  "no trades")

    print("\n" + "=" * 70)
    n = len(pooled_net)
    if n < 2:
        print(f"POOLED n={n} -- too few to summarise")
        return
    mean = statistics.mean(pooled_net)
    sd = statistics.stdev(pooled_net)
    se = sd / (n ** 0.5)
    print(f"POOLED n={n:5d}  gross={statistics.mean(pooled_gross):+.3f}R  "
          f"net={mean:+.3f}R  sd={sd:.3f}  t={mean / se:+.2f}  "
          f"95% CI [{mean - 1.96 * se:+.3f}, {mean + 1.96 * se:+.3f}]  "
          f"total={sum(pooled_net):+.1f}R")


if __name__ == "__main__":
    main()
