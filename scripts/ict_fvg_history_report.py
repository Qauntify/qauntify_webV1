"""ict_fvg backtested over the full verified Binance history (~8.9 years).

ict_fvg runs live on the super_scalp session (5m, gated on 15m HTF trend) and
has never been measured over long history before now -- flagged as an open
follow-up in docs/cloud-mss-backtest-results.md since that report's own
measurement work. It is also the fastest timeframe in the engine, where cost
drag is worst.

Same data and harness as scripts/bbma_history_report.py: SHA256-verified
monthly archives (scripts/history_provenance.py -- run that first if you have
not), replayed through backtest_windowed so a setup only counts here if it
would have fired live.

Binance lists no gold, so XAUUSD (also live on this session) is not covered
here -- see signals.analysis.backtest.main with STRATEGY_TIMEFRAMES["ict_fvg"]
for a shorter, live-API-paginated check instead.

WINDOW=200 matches ScanConfig.candle_limit-1, the closed bars a live 5m scan
actually sees (ict_fvg's own MIN_CANDLES=25 floor is well under this, so no
override is needed the way orb_rvol/cloud_mss needed one).

`super_scalp` (5m ict_fvg) is the only session in this engine with two extra
DETERMINISTIC hard gates in front of the detector, in signals/pipeline/scan.py:
`_super_scalp_session_gate` (only scans during London/NY liquid hours,
scalp_session_active()) and `_htf_opposes_setup` (rejects a setup whose
direction directly opposes the 15m HTF trend). Both are replicated here via
`gate=` so a trade only counts if super_scalp would actually have taken it --
skipping them would measure a strategy that isn't the one running live. The
probabilistic LLM confirm gate is still not simulated (never has been, in any
report in this repo -- see signals/analysis/backtest.py's module docstring).

Usage: .venv/bin/python -m scripts.ict_fvg_history_report
"""
import statistics
from datetime import datetime, timezone

import requests

from signals.analysis.backtest import backtest_windowed, htf_trend_series
from signals.analysis.history import load_history
from signals.analysis.indicators import atr
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
    """Mirrors scan.py's two hard gates for 5m ict_fvg exactly."""
    now = datetime.fromtimestamp(candle.open_time / 1000, tz=timezone.utc)
    if not scalp_session_active(now):
        return False
    htf_trend = setup.indicators.get("htf_trend")
    return not _htf_opposes_setup(setup.direction, htf_trend)


def main():
    session = requests.Session()
    cache = {}
    pooled_gross, pooled_net = [], []

    print("ict_fvg over the full verified Binance history. Scale-out model: "
          "1/3 at each of TP1/TP2/TP3 (0.5R/1R/2R), fixed stop as published.")
    print(f"{WINDOW}-bar rolling window (matches ScanConfig.candle_limit-1 -- "
          "the live scan's own view). Gated on London/NY liquid hours and "
          "hard HTF-opposition reject, exactly as super_scalp runs live.\n")
    print(f"{'symbol':7} {'years':>6} {'bars':>7} {'trades':>7} {'tp1%':>6} "
          f"{'tp3%':>6} {'gross':>7} {'net':>7} {'totR':>9}")
    print("-" * 70)

    for symbol in SYMBOLS:
        candles = load_history(symbol, TIMEFRAME, session=session)
        cache[(symbol, TIMEFRAME)] = candles
        htf_candles = load_history(symbol, CONFLUENCE_TIMEFRAME, session=session)
        cache[(symbol, CONFLUENCE_TIMEFRAME)] = htf_candles

        highs = [c.high for c in candles]
        lows = [c.low for c in candles]
        closes = [c.close for c in candles]
        atr14 = atr(highs, lows, closes, 14)
        trends = htf_trend_series(candles, htf_candles, CONFLUENCE_MINUTES)

        out = backtest_windowed(detect_setup, symbol, candles, atr14, trends,
                                window=WINDOW, max_hold=MAX_HOLD,
                                gate=_super_scalp_gate)
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
