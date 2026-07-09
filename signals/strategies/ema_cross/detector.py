"""EMA 9/21 crossover with RSI, MACD, ADX regime, and HTF-trend filters."""
from signals.models import CandidateSetup

CROSS_LOOKBACK = 3
SWING_WINDOW = 10
ATR_STOP_BUFFER = 0.5
RISK_REWARD = 2.0
RSI_OVERBOUGHT = 70.0
RSI_OVERSOLD = 30.0
# Below this, ADX marks a non-trending/ranging market — the exact regime
# where EMA crossovers whipsaw most. 20 is the standard Wilder threshold
# separating trending from ranging conditions.
ADX_TREND_MIN = 20.0


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


def detect_setup(symbol, candles, ema9, ema21, rsi14, macd_hist, atr14,
                 adx14=None, htf_trend=None):
    """Return a CandidateSetup if indicators align, else None.

    `adx14`, when given, gates both directions on a trending regime
    (ADX >= ADX_TREND_MIN) — omit it (None) to skip that filter, e.g. when
    ADX isn't available yet. `htf_trend`, when given ("up"/"down"), gates
    the setup to only fire with a higher-timeframe trend it agrees with —
    omit it to skip that filter too. Both default to None so existing
    callers that don't supply them see unchanged behavior.
    """
    if None in (ema9[-1], ema21[-1], rsi14[-1], macd_hist[-1], atr14[-1]):
        return None
    if adx14 is not None and adx14[-1] is not None and adx14[-1] < ADX_TREND_MIN:
        return None
    entry = candles[-1].close
    indicators = {
        "ema9": ema9[-1],
        "ema21": ema21[-1],
        "rsi": rsi14[-1],
        "macd_hist": macd_hist[-1],
    }
    if adx14 is not None and adx14[-1] is not None:
        indicators["adx"] = adx14[-1]
    if htf_trend is not None:
        indicators["htf_trend"] = htf_trend
    recent = candles[-SWING_WINDOW:]

    # A cross within the lookback only counts while it still holds on the
    # current bar — a cross that already reversed has no trend to trade.
    if (crossed_above_within(ema9, ema21)
            and ema9[-1] > ema21[-1]
            and rsi14[-1] < RSI_OVERBOUGHT
            and macd_hist[-1] > 0
            and htf_trend != "down"):
        swing_low = min(c.low for c in recent)
        stop = swing_low - ATR_STOP_BUFFER * atr14[-1]
        if stop >= entry:
            return None
        take_profit = entry + RISK_REWARD * (entry - stop)
        return CandidateSetup(symbol, "long", entry, stop, take_profit, indicators)

    if (crossed_below_within(ema9, ema21)
            and ema9[-1] < ema21[-1]
            and rsi14[-1] > RSI_OVERSOLD
            and macd_hist[-1] < 0
            and htf_trend != "up"):
        swing_high = max(c.high for c in recent)
        stop = swing_high + ATR_STOP_BUFFER * atr14[-1]
        if stop <= entry:
            return None
        take_profit = entry - RISK_REWARD * (stop - entry)
        return CandidateSetup(symbol, "short", entry, stop, take_profit, indicators)

    return None
