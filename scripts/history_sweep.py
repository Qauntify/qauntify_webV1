"""Every rules strategy re-measured over the full verified Binance history.

The short sweeps that these strategies were judged on reached ~30 days at 1h,
because Kraken caps OHLC at 721 bars. That is a single market regime. BBMA's
four-month result inverted completely when re-run over nine years — the losing
pattern won and the winning one lost — so every strategy still resting on a
short sample is suspect until it has been re-measured.

Data provenance: scripts/history_provenance.py verifies each monthly archive
against Binance's published SHA256 and locates known market events (the 2021
all-time high, Black Thursday) at their correct dates. Run it first.

Only BTC and ETH can be extended: Binance lists no gold or GBP, so XAUUSD and
GBPUSD results elsewhere remain on ~4 months and are not comparable to these.

A strategy whose module is absent is reported as unavailable rather than
skipped silently — `orb_rvol` currently lives only on an unmerged branch.

Usage: .venv/bin/python -m scripts.history_sweep
"""
import importlib
import statistics

import requests

from signals.backtest import backtest_windowed, htf_trend_series
from signals.history import load_history
from signals.indicators import atr
from signals.r_model import MAKER_BPS

SYMBOLS = ("BTCUSD", "ETHUSD")
TF_MINUTES = {"15m": 15, "1h": 60, "4h": 240, "1d": 1440}

# Each strategy replays in the configuration it ACTUALLY RUNS IN, not the one
# signals/backtest.py registers — those disagree, and the live one is what
# matters. sr_zone is pinned to the 15m scalp session with NO confluence
# (models.TRADING_SESSIONS), while the backtest registry has it at 1h/4h.
#
# The fee tier is per strategy, not per symbol. Every market-entry detector
# crosses the spread and pays taker (the r_model default); sr_limit rests an
# order at a zone edge and earns maker. Charging sr_limit taker fees measures a
# strategy nobody would run — and that single choice flips its verdict.
STRATEGIES = (
    # (key, module path, timeframe, confluence tf or None, window, bps)
    ("sr_zone", "signals.strategies.sr_zone.detector", "15m", None, 200, None),
    ("sr_limit", "signals.strategies.sr_limit.detector", "1h", "4h", 200,
     MAKER_BPS),
    # ORB needs 400 bars of 15m history for its relative-volume baseline.
    ("orb_rvol", "signals.strategies.orb_rvol.detector", "15m", None, 450, None),
)

MAX_HOLD = 2000


def load_detector(module_path):
    """Return the module's `detect_setup`, or None when it is not present."""
    try:
        return importlib.import_module(module_path).detect_setup
    except (ImportError, AttributeError):
        return None


def _series(symbol, timeframe, session, cache):
    key = (symbol, timeframe)
    if key not in cache:
        cache[key] = load_history(symbol, timeframe, session=session)
    return cache[key]


def main():
    session = requests.Session()
    cache = {}

    print("All rules strategies over the full verified Binance history "
          "(BTC/ETH only — Binance lists no gold or FX).")
    print("Scale-out: 1/3 at each of TP1/TP2/TP3, under the FIXED stop the signal publishes. "
          "Net subtracts r_model round-trip costs.\n")
    print(f"{'strategy':10} {'symbol':7} {'tf':4} {'years':>6} {'bars':>7} "
          f"{'trades':>7} {'tp1%':>6} {'tp3%':>6} {'gross':>7} {'net':>7} "
          f"{'totR':>9}")
    print("-" * 92)

    pooled = {}
    for key, module_path, timeframe, confluence, window, bps in STRATEGIES:
        detector = load_detector(module_path)
        if detector is None:
            print(f"{key:10} UNAVAILABLE — {module_path} is not importable on "
                  f"this branch; cannot be measured")
            continue

        tier = "maker" if bps == MAKER_BPS else "taker"
        pooled[key] = {"gross": [], "net": [], "tier": tier}
        for symbol in SYMBOLS:
            candles = _series(symbol, timeframe, session, cache)
            atr14 = atr([c.high for c in candles], [c.low for c in candles],
                        [c.close for c in candles], 14)
            trends = [None] * len(candles)
            if confluence:
                trends = htf_trend_series(
                    candles, _series(symbol, confluence, session, cache),
                    TF_MINUTES[confluence])

            out = backtest_windowed(detector, symbol, candles, atr14, trends,
                                    window=window, max_hold=MAX_HOLD, bps=bps)
            gross, net = out["gross"], out["net"]
            trades = len(gross)
            pooled[key]["gross"] += gross
            pooled[key]["net"] += net

            years = ((candles[-1].open_time - candles[0].open_time)
                     / 1000 / 86400 / 365.25)
            if trades:
                print(f"{key:10} {symbol:7} {timeframe:4} {years:6.2f} "
                      f"{len(candles):7d} {trades:7d} "
                      f"{out['tp1_hits'] / trades * 100:5.1f}% "
                      f"{out['tp3_hits'] / trades * 100:5.1f}% "
                      f"{statistics.mean(gross):+6.3f}R "
                      f"{statistics.mean(net):+6.3f}R {sum(net):+8.1f}R")
            else:
                print(f"{key:10} {symbol:7} {timeframe:4} {years:6.2f} "
                      f"{len(candles):7d} {0:7d}   no trades")

    print("\n" + "=" * 92)
    print("POOLED (both symbols)")
    for key, data in pooled.items():
        net, n = data["net"], len(data["net"])
        if n < 2:
            print(f"  {key:10} n={n} — too few to summarise")
            continue
        mean = statistics.mean(net)
        se = statistics.stdev(net) / (n ** 0.5)
        verdict = "PROFITABLE" if mean - 1.96 * se > 0 else (
            "LOSING" if mean + 1.96 * se < 0 else "indistinguishable from zero")
        print(f"  {key:10} n={n:5d}  [{data['tier']}]  "
              f"gross={statistics.mean(data['gross']):+.3f}R  "
              f"net={mean:+.3f}R  t={mean / se:+.2f}  "
              f"95% CI [{mean - 1.96 * se:+.3f}, {mean + 1.96 * se:+.3f}]  "
              f"total={sum(net):+.1f}R  -> {verdict}")


if __name__ == "__main__":
    main()
