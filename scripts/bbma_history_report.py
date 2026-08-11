"""BBMA backtested over the full verified Binance history (~8.9 years).

The short sweep (scripts/bbma_report.py) could only reach ~4 months per symbol
because Kraken caps OHLC at 721 bars. Four months is one market regime, which
cannot distinguish a strategy that works from one that happened to suit a
quarter. This runs the same two detectors over 2017-08 to now: the 2018 bear,
the 2020 COVID crash, the 2021 bull, the 2022 LUNA/FTX collapse and the
recovery since.

Data provenance is established by scripts/history_provenance.py — SHA256
verification against Binance's published digests, plus known market events
located at their correct dates. Run that first if you have not.

TWO DELIBERATE DIFFERENCES FROM signals/backtest.py, both making this MORE
faithful to production rather than less:

  * ROLLING WINDOW. The live engine fetches ScanConfig.candle_limit (201) bars
    and computes indicators on the 200 closed ones. This replays with the same
    200-bar window, so a setup fires here only if it would have fired live.
    backtest.py instead passes the whole prefix, which no live scan ever sees —
    and on 77,000 bars that is also quadratic, taking hours to produce a less
    accurate answer.

  * BOUNDED HOLD. A trade is abandoned after MAX_HOLD bars rather than walked
    to the end of history, mirroring the way live signals expire (see
    TradingSession.max_open). It also keeps the forward slice bounded.

Usage: .venv/bin/python -m scripts.bbma_history_report
"""
import statistics

import requests

from signals.analysis.backtest import backtest_windowed, htf_trend_series
from signals.analysis.history import load_history
from signals.analysis.indicators import atr
from signals.strategies.bbma import detect_extreme, detect_reentry

# Binance lists no gold or GBP, so those two symbols cannot be extended past
# the short sweep. Stated here rather than silently omitted.
SYMBOLS = ("BTCUSD", "ETHUSD")
TIMEFRAMES = ("1h", "4h")
CONFLUENCE = {"1h": "4h", "4h": "1d"}
TF_MINUTES = {"1h": 60, "4h": 240, "1d": 1440}
DETECTORS = {"bbma_extreme": detect_extreme, "bbma_reentry": detect_reentry}
# bbma_extreme is counter-trend by design and takes no HTF gate.
GATED = frozenset({"bbma_reentry"})

# Matches ScanConfig.candle_limit - 1: the closed bars a live scan actually sees.
WINDOW = 200
# Longest a trade is carried before being treated as expired.
MAX_HOLD = 2000


def _series(symbol, timeframe, session, cache):
    key = (symbol, timeframe)
    if key not in cache:
        cache[key] = load_history(symbol, timeframe, session=session)
    return cache[key]


def main():
    session = requests.Session()
    cache = {}
    pooled = {name: {"gross": [], "net": []} for name in DETECTORS}

    print("BBMA over the full verified Binance history. Scale-out model: 1/3 "
          "at each of TP1/TP2/TP3, under the FIXED stop the signal publishes.")
    print(f"{WINDOW}-bar rolling window (matches the live scan). Net subtracts "
          "r_model round-trip costs.\n")
    print(f"{'strategy':13} {'symbol':7} {'tf':3} {'years':>6} {'bars':>7} "
          f"{'trades':>7} {'tp1%':>6} {'tp3%':>6} {'gross':>7} {'net':>7} "
          f"{'totR':>9}")
    print("-" * 90)

    for name, detector in DETECTORS.items():
        for timeframe in TIMEFRAMES:
            for symbol in SYMBOLS:
                candles = _series(symbol, timeframe, session, cache)
                highs = [c.high for c in candles]
                lows = [c.low for c in candles]
                closes = [c.close for c in candles]
                atr14 = atr(highs, lows, closes, 14)

                trends = [None] * len(candles)
                if name in GATED:
                    htf = CONFLUENCE[timeframe]
                    htf_candles = _series(symbol, htf, session, cache)
                    trends = htf_trend_series(
                        candles, htf_candles, TF_MINUTES[htf])

                out = backtest_windowed(detector, symbol, candles, atr14,
                                        trends, window=WINDOW,
                                        max_hold=MAX_HOLD)
                gross, net = out["gross"], out["net"]
                trades = len(gross)
                pooled[name]["gross"] += gross
                pooled[name]["net"] += net

                years = ((candles[-1].open_time - candles[0].open_time)
                         / 1000 / 86400 / 365.25)
                if trades:
                    print(f"{name:13} {symbol:7} {timeframe:3} {years:6.2f} "
                          f"{len(candles):7d} {trades:7d} "
                          f"{out['tp1_hits'] / trades * 100:5.1f}% "
                          f"{out['tp3_hits'] / trades * 100:5.1f}% "
                          f"{statistics.mean(gross):+6.3f}R "
                          f"{statistics.mean(net):+6.3f}R "
                          f"{sum(net):+8.1f}R")
                else:
                    print(f"{name:13} {symbol:7} {timeframe:3} {years:6.2f} "
                          f"{len(candles):7d} {0:7d}   no trades")

    print("\n" + "=" * 90)
    print("POOLED (all symbols and timeframes)")
    for name, data in pooled.items():
        net = data["net"]
        n = len(net)
        if n < 2:
            print(f"  {name:13} n={n} — too few to summarise")
            continue
        mean = statistics.mean(net)
        sd = statistics.stdev(net)
        se = sd / (n ** 0.5)
        print(f"  {name:13} n={n:5d}  gross={statistics.mean(data['gross']):+.3f}R  "
              f"net={mean:+.3f}R  sd={sd:.3f}  t={mean / se:+.2f}  "
              f"95% CI [{mean - 1.96 * se:+.3f}, {mean + 1.96 * se:+.3f}]  "
              f"total={sum(net):+.1f}R")


if __name__ == "__main__":
    main()
