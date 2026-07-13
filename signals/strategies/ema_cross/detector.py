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
# Cap stop distance so late entries cannot invent oversized 2R targets.
MAX_STOP_ATR = 2.5
# If price has already traveled this many ATRs from the cross-bar close,
# the setup is too late for a market entry at the latest close.
MAX_ENTRY_DRIFT_ATR = 1.0


def crossed_above_within(fast, slow, lookback=CROSS_LOOKBACK):
    """True if `fast` crossed above `slow` on any of the last `lookback` bars."""
    return _latest_cross_index(fast, slow, lookback, above=True) is not None


def crossed_below_within(fast, slow, lookback=CROSS_LOOKBACK):
    """True if `fast` crossed below `slow` on any of the last `lookback` bars."""
    return _latest_cross_index(fast, slow, lookback, above=False) is not None


def _latest_cross_index(fast, slow, lookback, *, above: bool) -> int | None:
    n = len(fast)
    for i in range(n - 1, max(0, n - lookback) - 1, -1):
        if None in (fast[i - 1], slow[i - 1], fast[i], slow[i]):
            continue
        if above and fast[i - 1] <= slow[i - 1] and fast[i] > slow[i]:
            return i
        if not above and fast[i - 1] >= slow[i - 1] and fast[i] < slow[i]:
            return i
    return None


def _risk_ok(entry: float, stop: float, atr_value: float) -> bool:
    if atr_value <= 0:
        return False
    return abs(entry - stop) / atr_value <= MAX_STOP_ATR


def _entry_still_near_cross(entry: float, cross_close: float, atr_value: float) -> bool:
    if atr_value <= 0:
        return False
    return abs(entry - cross_close) / atr_value <= MAX_ENTRY_DRIFT_ATR


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
    atr_value = atr14[-1]
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
    cross_up = _latest_cross_index(ema9, ema21, CROSS_LOOKBACK, above=True)
    if (cross_up is not None
            and ema9[-1] > ema21[-1]
            and rsi14[-1] < RSI_OVERBOUGHT
            and macd_hist[-1] > 0
            and htf_trend != "down"
            and _entry_still_near_cross(entry, candles[cross_up].close, atr_value)):
        swing_low = min(c.low for c in recent)
        stop = swing_low - ATR_STOP_BUFFER * atr_value
        if stop >= entry or not _risk_ok(entry, stop, atr_value):
            return None
        take_profit = entry + RISK_REWARD * (entry - stop)
        return CandidateSetup(symbol, "long", entry, stop, take_profit, indicators)

    cross_down = _latest_cross_index(ema9, ema21, CROSS_LOOKBACK, above=False)
    if (cross_down is not None
            and ema9[-1] < ema21[-1]
            and rsi14[-1] > RSI_OVERSOLD
            and macd_hist[-1] < 0
            and htf_trend != "up"
            and _entry_still_near_cross(entry, candles[cross_down].close, atr_value)):
        swing_high = max(c.high for c in recent)
        stop = swing_high + ATR_STOP_BUFFER * atr_value
        if stop <= entry or not _risk_ok(entry, stop, atr_value):
            return None
        take_profit = entry - RISK_REWARD * (stop - entry)
        return CandidateSetup(symbol, "short", entry, stop, take_profit, indicators)

    return None
