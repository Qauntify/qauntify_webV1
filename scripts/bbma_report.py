"""Backtest sweep for the two BBMA detectors.

Reports each pattern separately, on each symbol, at each timeframe, gross AND
net of round-trip costs. The split matters: `bbma_extreme` fades a move and
`bbma_reentry` follows one, so a single blended number could hide a profitable
half behind a losing one.

Read the trade count before the expectancy. Kraken caps OHLC at 721 bars, so a
1h row spans about 30 days and a 4h row about 120 — thin enough that a handful
of trades proves nothing either way.

Usage: .venv/bin/python -m scripts.bbma_report
"""
import requests

from signals.backtest import backtest_strategy
from signals.clients.market import fetch_candles

STRATEGIES = ("bbma_extreme", "bbma_reentry")
SYMBOLS = ("BTCUSD", "ETHUSD", "XAUUSD")
# 15m is omitted deliberately — see the module docstring.
TIMEFRAMES = ("1h", "4h")
# One step up for the higher-timeframe trend gate.
CONFLUENCE = {"1h": "4h", "4h": "1d"}
TF_MINUTES = {"15m": 15, "1h": 60, "4h": 240, "1d": 1440}
# bbma_extreme is counter-trend by design and takes no HTF gate.
GATED = frozenset({"bbma_reentry"})
# Kraken caps at 721 regardless; ask for everything each source will serve.
CANDLE_LIMIT = 5000


def htf_for(strategy, timeframe):
    """The confluence timeframe for one row, or None when the strategy is
    ungated."""
    if strategy not in GATED:
        return None
    return CONFLUENCE.get(timeframe)


def _row(strategy, symbol, timeframe, session):
    htf = htf_for(strategy, timeframe)
    candles = fetch_candles(symbol, timeframe, CANDLE_LIMIT,
                            session=session)[:-1]
    htf_candles = None
    if htf is not None:
        htf_candles = fetch_candles(symbol, htf, CANDLE_LIMIT,
                                    session=session)[:-1]
    stats = backtest_strategy(
        strategy, symbol, candles,
        htf_candles=htf_candles,
        htf_minutes=TF_MINUTES[htf] if htf else None,
    )
    stats["bars"] = len(candles)
    return stats


def main():
    session = requests.Session()
    print("Scale-out model: 1/3 booked at each of TP1/TP2/TP3, under the "
          "FIXED stop the signal publishes. Net subtracts r_model round-trip costs.")
    print("bbma_extreme ladder is 0.5/1/1.5R; bbma_reentry is 1/2/3R.")
    print(f"{'strategy':13} {'symbol':7} {'tf':3} {'bars':>5} {'trades':>6} "
          f"{'tp1%':>6} {'tp3%':>6} {'gross':>7} {'net':>7} {'totR':>8}")
    print("-" * 78)
    for strategy in STRATEGIES:
        for timeframe in TIMEFRAMES:
            for symbol in SYMBOLS:
                try:
                    s = _row(strategy, symbol, timeframe, session)
                except Exception as exc:
                    print(f"{strategy:13} {symbol:7} {timeframe:3} "
                          f"data unavailable ({type(exc).__name__}: {exc})")
                    continue
                print(f"{strategy:13} {symbol:7} {timeframe:3} {s['bars']:5d} "
                      f"{s['trades']:6d} {s['tp1_rate'] * 100:5.1f}% "
                      f"{s['tp3_rate'] * 100:5.1f}% "
                      f"{s['expectancy_r']:+6.2f}R {s['net_expectancy_r']:+6.2f}R "
                      f"{s['total_r']:+7.1f}R")


if __name__ == "__main__":
    main()
