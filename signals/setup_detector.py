"""Derives a candidate trade setup from candles + precomputed indicators."""
from signals.models import CandidateSetup

CROSS_LOOKBACK = 3
SWING_WINDOW = 10
ATR_STOP_BUFFER = 0.5
RISK_REWARD = 2.0
RSI_OVERBOUGHT = 70.0
RSI_OVERSOLD = 30.0


def crossed_above_within(fast, slow, lookback=CROSS_LOOKBACK):
    """True if `fast` crossed above `slow` on any of the last `lookback` bars."""
    n = len(fast)
    for i in range(max(1, n - lookback), n):
        if None in (fast[i - 1], slow[i - 1], fast[i], slow[i]):
            continue
        if fast[i - 1] <= slow[i - 1] and fast[i] > slow[i]:
            return True
    return False


def crossed_below_within(fast, slow, lookback=CROSS_LOOKBACK):
    """True if `fast` crossed below `slow` on any of the last `lookback` bars."""
    n = len(fast)
    for i in range(max(1, n - lookback), n):
        if None in (fast[i - 1], slow[i - 1], fast[i], slow[i]):
            continue
        if fast[i - 1] >= slow[i - 1] and fast[i] < slow[i]:
            return True
    return False


def detect_setup(symbol, candles, ema9, ema21, rsi14, macd_hist, atr14):
    """Return a CandidateSetup if indicators align, else None."""
    if None in (ema9[-1], ema21[-1], rsi14[-1], macd_hist[-1], atr14[-1]):
        return None
    entry = candles[-1].close
    indicators = {
        "ema9": ema9[-1],
        "ema21": ema21[-1],
        "rsi": rsi14[-1],
        "macd_hist": macd_hist[-1],
    }
    recent = candles[-SWING_WINDOW:]

    if (crossed_above_within(ema9, ema21)
            and rsi14[-1] < RSI_OVERBOUGHT
            and macd_hist[-1] > 0):
        swing_low = min(c.low for c in recent)
        stop = swing_low - ATR_STOP_BUFFER * atr14[-1]
        if stop >= entry:
            return None
        take_profit = entry + RISK_REWARD * (entry - stop)
        return CandidateSetup(symbol, "long", entry, stop, take_profit, indicators)

    if (crossed_below_within(ema9, ema21)
            and rsi14[-1] > RSI_OVERSOLD
            and macd_hist[-1] < 0):
        swing_high = max(c.high for c in recent)
        stop = swing_high + ATR_STOP_BUFFER * atr14[-1]
        if stop <= entry:
            return None
        take_profit = entry - RISK_REWARD * (stop - entry)
        return CandidateSetup(symbol, "short", entry, stop, take_profit, indicators)

    return None
