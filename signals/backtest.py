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


def backtest_strategy(strategy, symbol, candles, *, warmup=DEFAULT_WARMUP):
    """Backtest one strategy on one symbol's candle history.

    Indicators are causal, so they're computed once on the full series and
    sliced per bar — the value at index i depends only on data up to i, so a
    slice matches recomputing on candles[:i+1]. Returns `summarize(...)` stats.
    """
    n = len(candles)
    if n <= warmup + 1:
        return summarize([])
    closes = [c.close for c in candles]
    highs = [c.high for c in candles]
    lows = [c.low for c in candles]
    ema9 = ema(closes, 9)
    ema21 = ema(closes, 21)
    rsi14 = rsi(closes, 14)
    macd_hist = macd_histogram(closes)
    atr14 = atr(highs, lows, closes, 14)
    adx14 = adx(highs, lows, closes, 14)

    results = []
    i = warmup
    while i < n - 1:
        end = i + 1
        setup = detect_setup(
            strategy, symbol, candles[:end],
            ema9[:end], ema21[:end], rsi14[:end], macd_hist[:end], atr14[:end],
            adx14=adx14[:end], htf_trend=None, h1_candles=None,
        )
        if setup is None:
            i += 1
            continue
        outcome, bars = simulate_trade(
            setup.direction, setup.entry, setup.stop_loss, setup.take_profit,
            candles[end:],
        )
        if outcome == "open":
            break  # ran out of forward data — stop rather than count a phantom
        results.append(
            realized_r(setup.direction, setup.entry, setup.stop_loss,
                       setup.take_profit, outcome)
        )
        i = end + bars  # resume after the closed trade (non-overlapping)
    return summarize(results)


def main():
    import requests

    from signals.market_client import fetch_candles

    session = requests.Session()
    print(f"{'strategy':10} {'symbol':7} {'tf':3} {'trades':>6} "
          f"{'win%':>6} {'exp/R':>7} {'total/R':>8}")
    print("-" * 56)
    for strategy, timeframe in STRATEGY_TIMEFRAMES.items():
        for symbol in DEFAULT_SYMBOLS:
            try:
                candles = fetch_candles(
                    symbol, timeframe, DEFAULT_CANDLE_LIMIT, session=session,
                )[:-1]  # drop the still-forming last bar
            except Exception as exc:
                print(f"{strategy:10} {symbol:7} {timeframe:3} "
                      f"data unavailable ({type(exc).__name__})")
                continue
            s = backtest_strategy(strategy, symbol, candles)
            print(f"{strategy:10} {symbol:7} {timeframe:3} {s['trades']:6d} "
                  f"{s['win_rate'] * 100:5.1f}% {s['expectancy_r']:+6.2f}R "
                  f"{s['total_r']:+7.1f}R")


if __name__ == "__main__":
    main()
