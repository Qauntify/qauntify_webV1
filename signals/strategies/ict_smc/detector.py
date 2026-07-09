"""ICT / SMC: liquidity sweep followed by structure shift (CHoCH)."""
from signals.models import Candle, CandidateSetup

PIVOT_LEFT = 2
PIVOT_RIGHT = 2
STRUCTURE_LOOKBACK = 60
MIN_CANDLES = 25
SWEEP_LOOKBACK = 12
CHOCH_LOOKBACK = 5
ATR_STOP_BUFFER = 0.5
RISK_REWARD = 2.0
# A tight PIVOT_LEFT/RIGHT window flags almost any small wick past a prior
# swing point as a "sweep." Requiring the wick to clear the level by at
# least this fraction of ATR filters that noise out, keeping only sweeps
# large enough to plausibly be a genuine liquidity grab.
MIN_SWEEP_ATR_FRACTION = 0.15


def pivot_lows(candles: list[Candle], left=PIVOT_LEFT, right=PIVOT_RIGHT) -> list[int]:
    """Indices of swing lows (local minima)."""
    pivots: list[int] = []
    for i in range(left, len(candles) - right):
        low = candles[i].low
        if all(low < candles[j].low for j in range(i - left, i)):
            if all(low <= candles[j].low for j in range(i + 1, i + right + 1)):
                pivots.append(i)
    return pivots


def pivot_highs(candles: list[Candle], left=PIVOT_LEFT, right=PIVOT_RIGHT) -> list[int]:
    """Indices of swing highs (local maxima)."""
    pivots: list[int] = []
    for i in range(left, len(candles) - right):
        high = candles[i].high
        if all(high > candles[j].high for j in range(i - left, i)):
            if all(high >= candles[j].high for j in range(i + 1, i + right + 1)):
                pivots.append(i)
    return pivots


def _recent_pivot_level(candles, pivot_indices, before_index, *, kind):
    for idx in reversed(pivot_indices):
        if idx < before_index:
            if kind == "low":
                return idx, candles[idx].low
            return idx, candles[idx].high
    return None, None


def detect_setup(symbol, candles, atr14):
    """Return a CandidateSetup on liquidity sweep + CHoCH, else None."""
    if len(candles) < MIN_CANDLES or atr14[-1] is None:
        return None

    window = candles[-STRUCTURE_LOOKBACK:]
    lows = pivot_lows(window)
    highs = pivot_highs(window)
    if not lows or not highs:
        return None

    entry = candles[-1].close
    atr_value = atr14[-1]
    sweep_start = max(0, len(window) - SWEEP_LOOKBACK)

    # Bullish: sweep below swing low, close back above, then break swing high.
    for sweep_i in range(sweep_start, len(window) - 1):
        pivot_idx, swing_low = _recent_pivot_level(
            window, lows, sweep_i, kind="low",
        )
        if pivot_idx is None or swing_low is None:
            continue
        bar = window[sweep_i]
        if bar.low >= swing_low or bar.close <= swing_low:
            continue
        if swing_low - bar.low < MIN_SWEEP_ATR_FRACTION * atr_value:
            continue
        choch_slice = window[sweep_i + 1:sweep_i + 1 + CHOCH_LOOKBACK]
        if not choch_slice:
            continue
        _, swing_high = _recent_pivot_level(
            window, highs, sweep_i, kind="high",
        )
        if swing_high is None:
            continue
        if not any(c.close > swing_high for c in choch_slice):
            continue
        stop = bar.low - ATR_STOP_BUFFER * atr_value
        if stop >= entry:
            continue
        take_profit = entry + RISK_REWARD * (entry - stop)
        indicators = {
            "strategy": "ict_smc",
            "structure": "bullish_choch",
            "sweep_level": swing_low,
            "choch_level": swing_high,
            "sweep_low": bar.low,
            "atr": atr_value,
        }
        return CandidateSetup(
            symbol, "long", entry, stop, take_profit, indicators,
        )

    # Bearish: sweep above swing high, close back below, then break swing low.
    for sweep_i in range(sweep_start, len(window) - 1):
        pivot_idx, swing_high = _recent_pivot_level(
            window, highs, sweep_i, kind="high",
        )
        if pivot_idx is None or swing_high is None:
            continue
        bar = window[sweep_i]
        if bar.high <= swing_high or bar.close >= swing_high:
            continue
        if bar.high - swing_high < MIN_SWEEP_ATR_FRACTION * atr_value:
            continue
        choch_slice = window[sweep_i + 1:sweep_i + 1 + CHOCH_LOOKBACK]
        if not choch_slice:
            continue
        _, swing_low = _recent_pivot_level(
            window, lows, sweep_i, kind="low",
        )
        if swing_low is None:
            continue
        if not any(c.close < swing_low for c in choch_slice):
            continue
        stop = bar.high + ATR_STOP_BUFFER * atr_value
        if stop <= entry:
            continue
        take_profit = entry - RISK_REWARD * (stop - entry)
        indicators = {
            "strategy": "ict_smc",
            "structure": "bearish_choch",
            "sweep_level": swing_high,
            "choch_level": swing_low,
            "sweep_high": bar.high,
            "atr": atr_value,
        }
        return CandidateSetup(
            symbol, "short", entry, stop, take_profit, indicators,
        )

    return None
