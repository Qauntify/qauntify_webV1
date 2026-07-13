"""ICT / SMC: liquidity sweep followed by structure shift (CHoCH)."""
from signals.models import Candle, CandidateSetup

PIVOT_LEFT = 2
PIVOT_RIGHT = 2
STRUCTURE_LOOKBACK = 60
MIN_CANDLES = 25
SWEEP_LOOKBACK = 12
CHOCH_LOOKBACK = 5
# CHoCH must complete within this many bars of the latest closed candle,
# otherwise the setup is stale relative to a market-order entry.
MAX_BARS_SINCE_CHOCH = 3
ATR_STOP_BUFFER = 0.5
RISK_REWARD = 2.0
# Reject setups whose stop is farther than this many ATRs from entry —
# otherwise 2R targets become unrealistic for a late market entry.
MAX_STOP_ATR = 2.0
ADX_TREND_MIN = 20.0
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


def _choch_bar_index(choch_slice, sweep_i, predicate) -> int | None:
    for offset, candle in enumerate(choch_slice):
        if predicate(candle):
            return sweep_i + 1 + offset
    return None


def _risk_ok(entry: float, stop: float, atr_value: float) -> bool:
    if atr_value <= 0:
        return False
    return abs(entry - stop) / atr_value <= MAX_STOP_ATR


def detect_setup(symbol, candles, atr14, adx14=None, htf_trend=None):
    """Return a CandidateSetup on liquidity sweep + CHoCH, else None.

    Prefers the newest valid sweep in the lookback so entry at the latest
    close is not paired with an ancient stop. `adx14`/`htf_trend` apply the
    same regime/confluence gates as ema_cross when provided.
    """
    if len(candles) < MIN_CANDLES or atr14[-1] is None:
        return None
    if adx14 is not None and adx14[-1] is not None and adx14[-1] < ADX_TREND_MIN:
        return None

    window = candles[-STRUCTURE_LOOKBACK:]
    lows = pivot_lows(window)
    highs = pivot_highs(window)
    if not lows or not highs:
        return None

    entry = candles[-1].close
    atr_value = atr14[-1]
    last_i = len(window) - 1
    sweep_start = max(0, len(window) - SWEEP_LOOKBACK)

    # Newest sweep first — stale structure + fresh entry is the failure mode.
    for sweep_i in range(len(window) - 2, sweep_start - 1, -1):
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
        choch_i = _choch_bar_index(
            choch_slice, sweep_i, lambda c: c.close > swing_high,
        )
        if choch_i is None:
            continue
        if last_i - choch_i > MAX_BARS_SINCE_CHOCH:
            continue
        if htf_trend == "down":
            continue
        stop = bar.low - ATR_STOP_BUFFER * atr_value
        if stop >= entry or not _risk_ok(entry, stop, atr_value):
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
        if adx14 is not None and adx14[-1] is not None:
            indicators["adx"] = adx14[-1]
        if htf_trend is not None:
            indicators["htf_trend"] = htf_trend
        return CandidateSetup(
            symbol, "long", entry, stop, take_profit, indicators,
        )

    for sweep_i in range(len(window) - 2, sweep_start - 1, -1):
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
        choch_i = _choch_bar_index(
            choch_slice, sweep_i, lambda c: c.close < swing_low,
        )
        if choch_i is None:
            continue
        if last_i - choch_i > MAX_BARS_SINCE_CHOCH:
            continue
        if htf_trend == "up":
            continue
        stop = bar.high + ATR_STOP_BUFFER * atr_value
        if stop <= entry or not _risk_ok(entry, stop, atr_value):
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
        if adx14 is not None and adx14[-1] is not None:
            indicators["adx"] = adx14[-1]
        if htf_trend is not None:
            indicators["htf_trend"] = htf_trend
        return CandidateSetup(
            symbol, "short", entry, stop, take_profit, indicators,
        )

    return None
