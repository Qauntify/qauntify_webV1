"""Render annotated entry charts for real BBMA trades from verified history.

Replays `bbma_reentry` over the SHA256-verified Binance archives, walks each
setup forward to its actual outcome, and writes one PNG per trade showing the
full BBMA stack at the moment of entry — Bollinger envelope, the MA5/MA10
High-Low pairs, EMA50 — plus entry, stop and the three targets.

Every chart is a trade that really happened on real price data. The title
carries the realised R so an entry can be read against what followed it.

Usage:
    .venv/bin/python -m scripts.bbma_trade_shots
    .venv/bin/python -m scripts.bbma_trade_shots --count 10 --symbol BTCUSD \\
        --timeframe 1h --out artifacts/bbma-trades
"""
import argparse
import datetime as dt
from pathlib import Path

import requests

from signals.analysis.backtest import htf_trend_series, simulate_scaled
from signals.chart.plan import build_chart_plan
from signals.chart.render import render_chart
from signals.analysis.history import load_history
from signals.analysis.indicators import atr
from signals.models import Confirmation, make_signal
from signals.analysis.r_model import cost_r, scaled_r
from signals.strategies.bbma import detect_reentry

WINDOW = 200          # matches the live scan (ScanConfig.candle_limit - 1)
MAX_HOLD = 2000
CONFLUENCE = {"1h": "4h", "4h": "1d"}
TF_MINUTES = {"1h": 60, "4h": 240, "1d": 1440}


def _utc(ms):
    return dt.datetime.fromtimestamp(ms / 1000, dt.UTC)


def collect_trades(symbol, timeframe, session, count):
    """The `count` most recent bbma_reentry trades, each with its outcome."""
    candles = load_history(symbol, timeframe, session=session)
    highs = [c.high for c in candles]
    lows = [c.low for c in candles]
    closes = [c.close for c in candles]
    atr14 = atr(highs, lows, closes, 14)

    htf = CONFLUENCE[timeframe]
    trends = htf_trend_series(
        candles, load_history(symbol, htf, session=session), TF_MINUTES[htf])

    trades = []
    n = len(candles)
    i = WINDOW
    while i < n - 1:
        lo = i - WINDOW + 1
        setup = detect_reentry(symbol, candles[lo:i + 1], atr14[lo:i + 1],
                               htf_trend=trends[i])
        if setup is None:
            i += 1
            continue
        tps = list(setup.resolved_take_profits())
        reached, stopped, bars = simulate_scaled(
            setup.direction, setup.entry, setup.stop_loss, tps,
            candles[i + 1:i + 1 + MAX_HOLD])
        gross = scaled_r(setup.direction, setup.entry, setup.stop_loss, tps,
                         reached, stopped)
        trades.append({
            "setup": setup,
            "index": i,
            # The whole window the detector saw. render_chart displays only
            # the last RENDER_BARS, but the BBMA stack must be computed over
            # all of it or EMA50 is still warming up inside the view.
            "candles": candles[max(0, i - WINDOW + 1):i + 1],
            "reached": reached,
            "stopped": stopped,
            "gross": gross,
            "net": gross - cost_r(symbol, setup.entry, setup.stop_loss),
            "time": candles[i].open_time,
        })
        i = i + 1 + max(bars, 1)

    return trades[-count:]


def render_trade(trade, symbol, timeframe, out_dir, ordinal):
    """Write one annotated entry PNG. Returns the path."""
    setup = trade["setup"]
    net = trade["net"]
    verdict = "WIN" if net > 0 else ("LOSS" if net < 0 else "FLAT")
    stamp = _utc(trade["time"]).strftime("%Y-%m-%d_%H%M")

    # These are backtested trades with no LLM score, so confidence stays 0 and
    # the headline is supplied explicitly instead of rendering "0%".
    signal = make_signal(
        setup, Confirmation("confirm", 0, "backtest replay"),
        [], timeframe=timeframe,
    )
    plan = build_chart_plan(trade["candles"], signal)
    title = (f"{symbol} · {timeframe} · {setup.direction.upper()} · "
             f"BBMA Re-entry · {stamp.replace('_', ' ')} UTC · "
             f"{trade['reached']}/3 TP · {net:+.2f}R net")
    png = render_chart(trade["candles"], plan, signal, title=title)

    name = (f"{ordinal:02d}_{symbol}_{timeframe}_{stamp}_"
            f"{setup.direction}_{verdict}_{net:+.2f}R.png")
    path = out_dir / name
    path.write_bytes(png)
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--symbol", default="BTCUSD")
    parser.add_argument("--timeframe", default="1h", choices=("1h", "4h"))
    parser.add_argument("--out", default="artifacts/bbma-trades")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    session = requests.Session()

    print(f"Replaying bbma_reentry on {args.symbol} {args.timeframe} over "
          f"verified history…")
    trades = collect_trades(args.symbol, args.timeframe, session, args.count)
    if not trades:
        print("No trades found.")
        return

    print(f"\nRendering {len(trades)} entries to {out_dir}/\n")
    print(f"{'#':>3} {'entry time (UTC)':17} {'dir':5} {'entry':>12} "
          f"{'stop':>12} {'TPs hit':>7} {'net R':>7}")
    print("-" * 72)
    total = 0.0
    for ordinal, trade in enumerate(trades, start=1):
        path = render_trade(trade, args.symbol, args.timeframe, out_dir, ordinal)
        setup = trade["setup"]
        total += trade["net"]
        print(f"{ordinal:3d} {_utc(trade['time']):%Y-%m-%d %H:%M}  "
              f"{setup.direction:5} {setup.entry:12,.2f} "
              f"{setup.stop_loss:12,.2f} {trade['reached']:4d}/3 "
              f"{trade['net']:+6.2f}R")
        print(f"    -> {path.name}")

    wins = sum(1 for t in trades if t["net"] > 0)
    print("-" * 72)
    print(f"{len(trades)} trades · {wins} winners · total {total:+.2f}R net "
          f"· {total / len(trades):+.3f}R per trade")
    print(f"\nImages saved in {out_dir.resolve()}")


if __name__ == "__main__":
    main()
