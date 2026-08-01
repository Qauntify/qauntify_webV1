"""Render annotated entry charts for real cloud_mss trades.

Replays `cloud_mss` over the SHA256-verified Binance archives, walks each setup
forward to its actual outcome, and writes one PNG per trade showing the cloud
at the moment of entry — the band between the 1h Chandelier Exit and the 15m
LWMA200 — plus the CHoCH level, entry, stop and the three targets.

Differs from scripts/bbma_trade_shots.py in one way that matters: cloud_mss is
MULTI-TIMEFRAME. Each 15m bar is handed only the 1h candles that had CLOSED by
its open time, via `htf_close_index`. Passing the in-progress 1h candle would
be lookahead, and every chart would show a cloud the strategy could not have
seen.

Every chart is a trade that really happened on real price data. The title
carries the realised R so an entry can be read against what followed it.

Usage:
    .venv/bin/python -m scripts.cloud_mss_trade_shots
    .venv/bin/python -m scripts.cloud_mss_trade_shots --count 10 \\
        --symbol BTCUSD --out artifacts/cloud-mss-trades
"""
import argparse
import datetime as dt
from pathlib import Path

import requests

from signals.backtest import HTF_WINDOW, htf_close_index, simulate_scaled
from signals.chart.outcome_plan import build_outcome_plan
from signals.chart.plan import build_chart_plan
from signals.chart.render import render_chart, render_outcome_chart
from signals.history import binance_symbol, load_history
from signals.indicators import atr
from signals.market_client import fetch_candles
from signals.models import Confirmation, make_signal
from signals.r_model import cost_r, scaled_r
from signals.strategies.cloud_mss import detect_setup

PRIMARY = "15m"
HTF = "1h"
HTF_MINUTES = 60
# Matches _candle_limit_for("cloud_mss", cfg) minus the forming bar, so the
# replay sees exactly what a live scan sees.
WINDOW = 259
MAX_HOLD = 2000
# Bars of context shown before entry on the outcome chart. Enough to see the
# cloud rejection that set it up, without burying the resolution.
PRE_ENTRY_BARS = 20


def _utc(ms):
    return dt.datetime.fromtimestamp(ms / 1000, dt.UTC)


def load_series(symbol, timeframe, session):
    """Candles for `symbol`, preferring the verified deep archives.

    Binance lists no gold or FX, and signals/history.py refuses them rather
    than guessing at a similarly-named market. Those symbols fall back to the
    live source, which is far shallower — roughly a month of 15m gold against
    nine years of crypto. Returns (candles, source) so the caller can say which
    it used instead of presenting the two as equivalent.
    """
    try:
        binance_symbol(symbol)
    except ValueError:
        return fetch_candles(symbol, timeframe, 5000, session=session)[:-1], "live"
    return load_history(symbol, timeframe, session=session), "archive"


def collect_trades(symbol, session, count):
    """The `count` most recent cloud_mss trades, each with its outcome."""
    candles, source = load_series(symbol, PRIMARY, session)
    htf, _ = load_series(symbol, HTF, session)
    atr14 = atr([c.high for c in candles], [c.low for c in candles],
                [c.close for c in candles], 14)
    htf_index = htf_close_index(candles, htf, HTF_MINUTES)

    trades = []
    n = len(candles)
    i = WINDOW
    while i < n - 1:
        j = htf_index[i]
        if j < 0:
            i += 1
            continue
        lo = i - WINDOW + 1
        h1 = htf[max(0, j + 1 - HTF_WINDOW):j + 1]
        setup = detect_setup(symbol, candles[lo:i + 1], atr14[lo:i + 1],
                             h1_candles=h1)
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
            # Entry-bar context PLUS the forward path to resolution, so the
            # outcome chart can show what actually happened after entry.
            "path": candles[max(0, i - PRE_ENTRY_BARS):i + 1 + max(bars, 1)],
            "entry_time": candles[i].open_time,
            "stopped": stopped,
            # The whole window the detector saw. render_chart displays only the
            # last RENDER_BARS, but the LWMA200 must be computed over all of it
            # or it is still warming up inside the view.
            "candles": candles[lo:i + 1],
            "reached": reached,
            "gross": gross,
            "net": gross - cost_r(symbol, setup.entry, setup.stop_loss),
            "time": candles[i].open_time,
        })
        i = i + 1 + max(bars, 1)

    return trades[-count:], source, candles


def _outcome_of(trade):
    """(status, verdict) for a replayed trade.

    Three outcomes, not two. A trade that reached no target and was never
    stopped EXPIRED — calling that a stop, as the live outcome title does,
    would misreport it.
    """
    if trade["reached"] >= 3:
        return "tp3_hit", "TP3"
    if trade["stopped"]:
        return "sl_hit", f"SL-after-TP{trade['reached']}" if trade["reached"] else "SL"
    return "expired", "EXPIRED"


def render_trade(trade, symbol, out_dir, ordinal):
    """Write the entry chart and the outcome chart. Returns both paths."""
    setup = trade["setup"]
    net = trade["net"]
    status, verdict = _outcome_of(trade)
    stamp = _utc(trade["time"]).strftime("%Y-%m-%d_%H%M")
    stem = (f"{ordinal:02d}_{symbol}_{PRIMARY}_{stamp}_"
            f"{setup.direction}_{verdict}_{net:+.2f}R")

    # Backtested trades carry no LLM score, so confidence stays 0 and the
    # headline is supplied explicitly rather than rendering "0%".
    signal = make_signal(
        setup, Confirmation("confirm", 0, "backtest replay"),
        [], timeframe=PRIMARY,
    )
    side = setup.indicators.get("side", "cloud")
    head = (f"{symbol} · {PRIMARY} · {setup.direction.upper()} · "
            f"cloud_mss ({side}) · {stamp.replace('_', ' ')} UTC")

    entry_png = render_chart(
        trade["candles"], build_chart_plan(trade["candles"], signal), signal,
        title=f"{head} · SETUP",
    )
    entry_path = out_dir / f"{stem}_1setup.png"
    entry_path.write_bytes(entry_png)

    row = {
        "symbol": symbol, "timeframe": PRIMARY, "direction": setup.direction,
        "entry": setup.entry, "stop_loss": setup.stop_loss,
        "take_profit": setup.take_profit,
        "take_profit_2": setup.take_profit_2,
        "take_profit_3": setup.take_profit_3,
    }
    plan = build_outcome_plan(row, status, trade["path"], trade["entry_time"])
    if status == "expired":
        # build_outcome_plan draws a loss zone for anything that is not a win.
        # This trade was closed out flat, so that zone would be a fiction.
        plan = [a for a in plan if a.get("label") != "Loss"]
    tag = {"tp3_hit": "✓ TP3 HIT", "sl_hit": "✗ SL HIT",
           "expired": "— EXPIRED"}[status]
    outcome_png = render_outcome_chart(
        trade["path"], plan, row, trade["entry_time"], status,
        max_bars=len(trade["path"]),
        title=(f"{head} · {tag} · {trade['reached']}/3 TP banked · "
               f"{net:+.2f}R net"),
    )
    outcome_path = out_dir / f"{stem}_2outcome.png"
    outcome_path.write_bytes(outcome_png)
    return entry_path, outcome_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--symbol", default="BTCUSD")
    parser.add_argument("--out", default="artifacts/cloud-mss-trades")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    session = requests.Session()

    print(f"Replaying cloud_mss on {args.symbol} {PRIMARY} "
          f"(cloud from {HTF}) over verified history…")
    trades, source, candles = collect_trades(args.symbol, session, args.count)
    days = (candles[-1].open_time - candles[0].open_time) / 86_400_000
    label = ("SHA256-verified Binance archives" if source == "archive"
             else "live market feed (no deep archive for this symbol)")
    print(f"  source: {label} — {len(candles):,} bars, {days:.0f} days\n")
    if not trades:
        print("No trades found in the available history.")
        return

    print(f"\nRendering {len(trades)} trades "
          f"({len(trades) * 2} charts: setup + outcome) to {out_dir}/\n")
    print(f"{'#':>3} {'entry time (UTC)':17} {'side':9} {'dir':5} "
          f"{'entry':>12} {'stop':>12} {'TP':>5} {'net R':>7}")
    print("-" * 82)
    total = 0.0
    for ordinal, trade in enumerate(trades, start=1):
        entry_path, outcome_path = render_trade(
            trade, args.symbol, out_dir, ordinal)
        setup = trade["setup"]
        total += trade["net"]
        print(f"{ordinal:3d} {_utc(trade['time']):%Y-%m-%d %H:%M}  "
              f"{setup.indicators.get('side', '?'):9} {setup.direction:5} "
              f"{setup.entry:12,.2f} {setup.stop_loss:12,.2f} "
              f"{trade['reached']:3d}/3 {trade['net']:+6.2f}R")
        print(f"    -> {entry_path.name}")
        print(f"    -> {outcome_path.name}")

    wins = sum(1 for t in trades if t["net"] > 0)
    print("-" * 82)
    print(f"{len(trades)} trades · {wins} winners · total {total:+.2f}R net "
          f"· {total / len(trades):+.3f}R per trade")
    if source == "archive":
        print("\nThese are the LAST trades, not a sample of the strategy. The "
              "full 8.87-year measurement is -0.046R over 1,202 trades "
              "(docs/cloud-mss-backtest-results.md).")
    else:
        print(f"\nWARNING: {days:.0f} days of history, not the 8.87 years the "
              "crypto archives give. These charts are illustrations of what "
              "the setup looks like on this instrument — they are NOT a "
              "measurement and must not be read as one.")
    print(f"Images saved in {out_dir.resolve()}")


if __name__ == "__main__":
    main()
