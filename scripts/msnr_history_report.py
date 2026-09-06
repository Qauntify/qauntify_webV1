"""msnr backtested over the full verified Binance history (~8.9 years).

msnr runs live on the swing session (1h, gated on 4h HTF trend via EMA9/21)
and, like ict_fvg before this, had never been measured over long history --
the last of the three original live sessions to get this treatment (see
docs/ict-fvg-backtest-results.md's follow-ups).

Same harness as scripts/bbma_history_report.py / scripts/ict_fvg_history_report.py:
SHA256-verified monthly archives (scripts/history_provenance.py -- run that
first if you have not), replayed through backtest_windowed on a 200-bar
rolling window (matches ScanConfig.candle_limit-1, the closed bars a live 1h
scan actually sees; msnr's own MIN_CANDLES=40 is well under this).

Unlike ict_fvg's super_scalp, there is no extra pipeline-level hard gate for
the swing session in signals/pipeline/scan.py (checked: no session-hours or
HTF-hard-reject special case keyed on "1h"/"msnr"). msnr's HTF gate
(_long_ok/_short_ok) is already a hard filter INSIDE the detector itself, so
backtest_windowed's normal htf_trend plumbing already replicates live
behavior faithfully -- no gate= callback needed here.

Binance lists no gold, so XAUUSD (also live on this session) is not covered
here -- see signals.analysis.backtest.main for a shorter, live-API-paginated
check instead.

Usage: .venv/bin/python -m scripts.msnr_history_report
"""
import statistics

import requests

from signals.analysis.backtest import backtest_windowed, htf_trend_series
from signals.analysis.history import load_history
from signals.analysis.indicators import atr
from signals.strategies.msnr.detector import detect_setup

SYMBOLS = ("BTCUSD", "ETHUSD")
TIMEFRAME = "1h"
CONFLUENCE_TIMEFRAME = "4h"
CONFLUENCE_MINUTES = 240
WINDOW = 200
MAX_HOLD = 2000


def main():
    session = requests.Session()
    pooled_gross, pooled_net = [], []

    print("msnr over the full verified Binance history. Scale-out model: "
          "1/3 at each of TP1/TP2/TP3 (fixed stop as published).")
    print(f"{WINDOW}-bar rolling window (matches ScanConfig.candle_limit-1 -- "
          "the live scan's own view). Gated on 4h HTF trend (hard filter "
          "inside the detector), as live.\n")
    print(f"{'symbol':7} {'years':>6} {'bars':>7} {'trades':>7} {'tp1%':>6} "
          f"{'tp3%':>6} {'gross':>7} {'net':>7} {'totR':>9}")
    print("-" * 70)

    for symbol in SYMBOLS:
        candles = load_history(symbol, TIMEFRAME, session=session)
        htf_candles = load_history(symbol, CONFLUENCE_TIMEFRAME, session=session)

        highs = [c.high for c in candles]
        lows = [c.low for c in candles]
        closes = [c.close for c in candles]
        atr14 = atr(highs, lows, closes, 14)
        trends = htf_trend_series(candles, htf_candles, CONFLUENCE_MINUTES)

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
