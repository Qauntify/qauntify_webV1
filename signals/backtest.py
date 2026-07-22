"""Rules-only historical backtester.

Replays a strategy's `detect_setup` over historical candles and simulates
TP1/SL fills bar-by-bar, so you can see a strategy's edge (win-rate,
expectancy in R) before trusting its live signals. The LLM confirm step is
intentionally NOT run here — this measures the deterministic rules; the AI is
a separate live gate.

Assumptions (documented so results are read correctly):
- Entry at the setup's entry price (the signal bar's close).
- Exit at TP1 (win) or stop (loss), whichever the forward candles hit first.
- A single bar that spans BOTH stop and TP1 is scored as a stop (conservative
  — we can't see intrabar order, so assume the worst).
- Trades are non-overlapping: after one opens, scanning resumes only after it
  closes.
- No higher-timeframe confluence and no multi-timeframe strategies (ce_lwma
  needs H1 alignment — not covered here).

Usage: python -m signals.backtest
"""
from signals.indicators import adx, atr, ema, macd_histogram, rsi
from signals.strategies import detect_setup

# Default per-strategy timeframe (matches the live sessions) and warm-up bars
# before scanning begins (ADX needs 2*period; structure strategies want room).
STRATEGY_TIMEFRAMES = {
    "ict_fvg": "5m",
    "ema_cross": "1h",
    "ict_smc": "1h",
    "sr_zone": "1h",
}
DEFAULT_WARMUP = 60
DEFAULT_SYMBOLS = ("BTCUSD", "ETHUSD", "XAUUSD", "GBPUSD")
DEFAULT_CANDLE_LIMIT = 720

# Higher-timeframe confluence per strategy (matches the live sessions), so the
# backtest gates setups on HTF trend exactly as production does.
CONFLUENCE_TIMEFRAMES = {
    "ict_fvg": "15m",
    "ema_cross": "4h",
    "ict_smc": "4h",
    "sr_zone": "4h",
}
TF_MINUTES = {"5m": 5, "15m": 15, "1h": 60, "4h": 240}


def htf_trend_series(primary_candles, htf_candles, htf_minutes):
    """Per primary candle, the EMA9-vs-EMA21 trend of the most recent CLOSED
    higher-timeframe candle at that bar's open time.

    Returns a list aligned to `primary_candles` of "up" / "down" / None,
    matching how the live engine reads HTF confluence (None while warming up).
    Both series must be ascending by open_time.
    """
    htf_ms = htf_minutes * 60_000
    closes = [c.close for c in htf_candles]
    ema9 = ema(closes, 9)
    ema21 = ema(closes, 21)
    trends = []
    j = -1
    for bar in primary_candles:
        while (j + 1 < len(htf_candles)
               and htf_candles[j + 1].open_time + htf_ms <= bar.open_time):
            j += 1
        if j < 0 or ema9[j] is None or ema21[j] is None or ema9[j] == ema21[j]:
            trends.append(None)
        else:
            trends.append("up" if ema9[j] > ema21[j] else "down")
    return trends


def simulate_trade(direction, entry, stop, take_profit, future_candles):
    """Walk forward bars; return (outcome, bars_consumed).

    outcome is "win" (TP1 first), "loss" (stop first), or "open" (neither by
    end of data). The stop is checked before the target, so a bar that hits
    both is a loss — the conservative read when intrabar order is unknown.
    """
    for idx, bar in enumerate(future_candles, start=1):
        if direction == "long":
            hit_stop = bar.low <= stop
            hit_tp = bar.high >= take_profit
        else:
            hit_stop = bar.high >= stop
            hit_tp = bar.low <= take_profit
        if hit_stop:
            return "loss", idx
        if hit_tp:
            return "win", idx
    return "open", len(future_candles)


def realized_r(direction, entry, stop, take_profit, outcome):
    """Realized R-multiple: +reward/risk on a win, -1 on a loss, 0 if open."""
    risk = abs(entry - stop)
    if risk == 0:
        return 0.0
    if outcome == "win":
        return abs(take_profit - entry) / risk
    if outcome == "loss":
        return -1.0
    return 0.0


def simulate_scaled(direction, entry, stop, tps, future_candles):
    """Walk forward under a FIXED stop (matching the live outcome tracker).

    Returns (reached, stopped, bars): `reached` is how many ordered targets
    (0..len(tps)) price tagged before the stop; `stopped` is whether the stop
    was hit; `bars` is candles consumed. Stop wins same-candle ties, so a bar
    that spans both the stop and a target counts only the stop.
    """
    reached = 0
    for idx, bar in enumerate(future_candles, start=1):
        hit_stop = bar.low <= stop if direction == "long" else bar.high >= stop
        if hit_stop:
            return reached, True, idx
        for k in range(reached, len(tps)):
            hit_tp = bar.high >= tps[k] if direction == "long" else bar.low <= tps[k]
            if not hit_tp:
                break
            reached = k + 1
        if reached >= len(tps):
            return reached, False, idx
    return reached, False, len(future_candles)


def scaled_r(direction, entry, stop, tps, reached, stopped):
    """Realized R for a 1/len-at-each-target scale-out with the stop trailed to
    breakeven once the first target is booked.

    - Nothing reached + stopped → full -1R.
    - Each reached target books its slice at that target's R.
    - The unbooked remainder exits at breakeven (0R) on a later stop or expiry.
    """
    risk = abs(entry - stop)
    if risk == 0 or not tps:
        return 0.0

    def r_of(price):
        return (price - entry) / risk if direction == "long" else (entry - price) / risk

    portion = 1.0 / len(tps)
    booked = sum(portion * r_of(tps[k]) for k in range(reached))
    if reached >= len(tps):
        return booked
    if reached == 0 and stopped:
        return -1.0
    return booked  # remainder trails out at breakeven → contributes 0R


def summarize(r_multiples):
    """Aggregate a list of realized R-multiples into headline stats."""
    trades = len(r_multiples)
    if trades == 0:
        return {"trades": 0, "wins": 0, "losses": 0,
                "win_rate": 0.0, "expectancy_r": 0.0, "total_r": 0.0}
    wins = sum(1 for r in r_multiples if r > 0)
    total = sum(r_multiples)
    return {
        "trades": trades,
        "wins": wins,
        "losses": trades - wins,
        "win_rate": wins / trades,
        "expectancy_r": total / trades,
        "total_r": total,
    }


def backtest_strategy(strategy, symbol, candles, *, warmup=DEFAULT_WARMUP,
                      htf_candles=None, htf_minutes=None):
    """Backtest one strategy on one symbol's candle history.

    Indicators are causal, so they're computed once on the full series and
    sliced per bar — the value at index i depends only on data up to i, so a
    slice matches recomputing on candles[:i+1]. When `htf_candles`/`htf_minutes`
    are given, each setup is gated on the aligned higher-timeframe trend, as the
    live engine does. Returns `summarize(...)` stats plus tp1/tp3 reach rates.
    """
    n = len(candles)
    if n <= warmup + 1:
        stats = summarize([])
        stats["tp1_rate"] = 0.0
        stats["tp3_rate"] = 0.0
        return stats
    if htf_candles and htf_minutes:
        trends = htf_trend_series(candles, htf_candles, htf_minutes)
    else:
        trends = [None] * n
    closes = [c.close for c in candles]
    highs = [c.high for c in candles]
    lows = [c.low for c in candles]
    ema9 = ema(closes, 9)
    ema21 = ema(closes, 21)
    rsi14 = rsi(closes, 14)
    macd_hist = macd_histogram(closes)
    atr14 = atr(highs, lows, closes, 14)
    adx14 = adx(highs, lows, closes, 14)

    r_multiples = []
    tp1_hits = 0
    tp3_hits = 0
    i = warmup
    while i < n - 1:
        end = i + 1
        setup = detect_setup(
            strategy, symbol, candles[:end],
            ema9[:end], ema21[:end], rsi14[:end], macd_hist[:end], atr14[:end],
            adx14=adx14[:end], htf_trend=trends[i], h1_candles=None,
        )
        if setup is None:
            i += 1
            continue
        tps = list(setup.resolved_take_profits())
        reached, stopped, bars = simulate_scaled(
            setup.direction, setup.entry, setup.stop_loss, tps, candles[end:],
        )
        if reached == 0 and not stopped:
            break  # ran out of forward data with an undecided trade — stop
        r_multiples.append(
            scaled_r(setup.direction, setup.entry, setup.stop_loss, tps,
                     reached, stopped)
        )
        tp1_hits += 1 if reached >= 1 else 0
        tp3_hits += 1 if reached >= len(tps) else 0
        i = end + bars  # resume after the closed trade (non-overlapping)

    stats = summarize(r_multiples)
    trades = stats["trades"]
    stats["tp1_rate"] = tp1_hits / trades if trades else 0.0
    stats["tp3_rate"] = tp3_hits / trades if trades else 0.0
    return stats


def main():
    import requests

    from signals.market_client import fetch_candles

    session = requests.Session()
    print("Scale-out model: 1/3 booked at each of TP1/TP2/TP3, stop trails to "
          "breakeven after TP1. HTF confluence applied (as live).")
    print(f"{'strategy':10} {'symbol':7} {'tf':3} {'trades':>6} "
          f"{'tp1%':>6} {'tp3%':>6} {'exp/R':>7} {'total/R':>8}")
    print("-" * 64)
    for strategy, timeframe in STRATEGY_TIMEFRAMES.items():
        htf_tf = CONFLUENCE_TIMEFRAMES.get(strategy)
        htf_minutes = TF_MINUTES.get(htf_tf) if htf_tf else None
        for symbol in DEFAULT_SYMBOLS:
            try:
                candles = fetch_candles(
                    symbol, timeframe, DEFAULT_CANDLE_LIMIT, session=session,
                )[:-1]  # drop the still-forming last bar
                htf_candles = None
                if htf_tf:
                    htf_candles = fetch_candles(
                        symbol, htf_tf, DEFAULT_CANDLE_LIMIT, session=session,
                    )[:-1]
            except Exception as exc:
                print(f"{strategy:10} {symbol:7} {timeframe:3} "
                      f"data unavailable ({type(exc).__name__})")
                continue
            s = backtest_strategy(
                strategy, symbol, candles,
                htf_candles=htf_candles, htf_minutes=htf_minutes,
            )
            print(f"{strategy:10} {symbol:7} {timeframe:3} {s['trades']:6d} "
                  f"{s['tp1_rate'] * 100:5.1f}% {s['tp3_rate'] * 100:5.1f}% "
                  f"{s['expectancy_r']:+6.2f}R {s['total_r']:+7.1f}R")


if __name__ == "__main__":
    main()
