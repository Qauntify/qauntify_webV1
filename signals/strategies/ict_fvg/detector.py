"""ICT 5m super-scalp: liquidity sweep + CHoCH + Fair Value Gap retest.

No killzone / session-time filter — fires whenever structure + FVG align.
SL sits just beyond the sweep extreme; TP1/TP2/TP3 use short R multiples
(0.5 / 1.0 / 1.5) so risk is tighter than the swing ICT playbook.
"""
from signals.models import (
    SUPER_SCALP_TP1_R,
    SUPER_SCALP_TP2_R,
    SUPER_SCALP_TP3_R,
    CandidateSetup,
    take_profits_from_risk,
)
from signals.strategies.ict_smc.detector import (
    CHOCH_LOOKBACK,
    PIVOT_LEFT,
    PIVOT_RIGHT,
    STRUCTURE_LOOKBACK,
    SWEEP_LOOKBACK,
    _choch_bar_index,
    _recent_pivot_level,
    pivot_highs,
    pivot_lows,
)

# Super-scalp overrides — looser than swing ict_smc so 5m setups can print.
MAX_BARS_SINCE_CHOCH = 6
MIN_SWEEP_ATR_FRACTION = 0.08
ATR_STOP_BUFFER = 0.25
MAX_STOP_ATR = 2.5
MIN_CANDLES = 25
# FVG retest must still be relatively fresh vs the latest closed bar.
MAX_BARS_SINCE_RETEST = 5


def find_bullish_fvg(candles, start: int, end: int) -> tuple[int, float, float] | None:
    """Newest 3-candle bullish FVG in [start, end]: high[i-2] < low[i]."""
    start = max(start, 2)
    for i in range(end, start - 1, -1):
        if i < 2 or i >= len(candles):
            continue
        bottom = candles[i - 2].high
        top = candles[i].low
        if bottom < top:
            return i, bottom, top
    return None


def find_bearish_fvg(candles, start: int, end: int) -> tuple[int, float, float] | None:
    """Newest 3-candle bearish FVG in [start, end]: low[i-2] > high[i]."""
    start = max(start, 2)
    for i in range(end, start - 1, -1):
        if i < 2 or i >= len(candles):
            continue
        top = candles[i - 2].low
        bottom = candles[i].high
        if top > bottom:
            return i, bottom, top
    return None


def _retest_bullish(candles, fvg_i: int, gap_bottom: float, gap_top: float,
                    last_i: int) -> int | None:
    """Index of a bar after the FVG that traded into the gap from above."""
    for j in range(fvg_i + 1, last_i + 1):
        bar = candles[j]
        if bar.low <= gap_top and bar.high >= gap_bottom:
            return j
    return None


def _retest_bearish(candles, fvg_i: int, gap_bottom: float, gap_top: float,
                    last_i: int) -> int | None:
    for j in range(fvg_i + 1, last_i + 1):
        bar = candles[j]
        if bar.high >= gap_bottom and bar.low <= gap_top:
            return j
    return None


def _risk_ok(entry: float, stop: float, atr_value: float) -> bool:
    if atr_value <= 0:
        return False
    return abs(entry - stop) / atr_value <= MAX_STOP_ATR


def detect_setup(symbol, candles, atr14, htf_trend=None):
    """Return a CandidateSetup on sweep + CHoCH + FVG retest, else None.

    `htf_trend` (typically 15m) is a soft preference: with-trend setups are
    tried first, but against-trend patterns remain eligible. No ADX and no
    session-hour filter — any time the pattern prints is eligible.
    """
    if len(candles) < MIN_CANDLES or atr14[-1] is None:
        return None

    window = candles[-STRUCTURE_LOOKBACK:]
    lows = pivot_lows(window, left=PIVOT_LEFT, right=PIVOT_RIGHT)
    highs = pivot_highs(window, left=PIVOT_LEFT, right=PIVOT_RIGHT)
    if not lows or not highs:
        return None

    entry = candles[-1].close
    atr_value = atr14[-1]
    last_i = len(window) - 1
    sweep_start = max(0, len(window) - SWEEP_LOOKBACK)

    def _long_candidate():
        for sweep_i in range(len(window) - 2, sweep_start - 1, -1):
            _, swing_low = _recent_pivot_level(window, lows, sweep_i, kind="low")
            if swing_low is None:
                continue
            bar = window[sweep_i]
            if bar.low >= swing_low or bar.close <= swing_low:
                continue
            if swing_low - bar.low < MIN_SWEEP_ATR_FRACTION * atr_value:
                continue
            choch_slice = window[sweep_i + 1:sweep_i + 1 + CHOCH_LOOKBACK]
            if not choch_slice:
                continue
            _, swing_high = _recent_pivot_level(window, highs, sweep_i, kind="high")
            if swing_high is None:
                continue
            choch_i = _choch_bar_index(
                choch_slice, sweep_i, lambda c: c.close > swing_high,
            )
            if choch_i is None or last_i - choch_i > MAX_BARS_SINCE_CHOCH:
                continue

            fvg = find_bullish_fvg(window, max(sweep_i + 1, choch_i - 2), last_i)
            if fvg is None:
                continue
            fvg_i, gap_bottom, gap_top = fvg
            retest_i = _retest_bullish(window, fvg_i, gap_bottom, gap_top, last_i)
            if retest_i is None or last_i - retest_i > MAX_BARS_SINCE_RETEST:
                continue

            stop = bar.low - ATR_STOP_BUFFER * atr_value
            if stop >= entry or not _risk_ok(entry, stop, atr_value):
                continue
            tp1, tp2, tp3 = take_profits_from_risk(
                entry, stop, "long",
                r1=SUPER_SCALP_TP1_R, r2=SUPER_SCALP_TP2_R, r3=SUPER_SCALP_TP3_R,
            )
            indicators = {
                "strategy": "ict_fvg",
                "structure": "bullish_choch_fvg",
                "sweep_level": swing_low,
                "choch_level": swing_high,
                "sweep_low": bar.low,
                "fvg_bottom": gap_bottom,
                "fvg_top": gap_top,
                "atr": atr_value,
                "tp_r": [SUPER_SCALP_TP1_R, SUPER_SCALP_TP2_R, SUPER_SCALP_TP3_R],
            }
            if htf_trend is not None:
                indicators["htf_trend"] = htf_trend
            return CandidateSetup(
                symbol, "long", entry, stop, tp1, indicators,
                take_profit_2=tp2, take_profit_3=tp3,
            )
        return None

    def _short_candidate():
        for sweep_i in range(len(window) - 2, sweep_start - 1, -1):
            _, swing_high = _recent_pivot_level(window, highs, sweep_i, kind="high")
            if swing_high is None:
                continue
            bar = window[sweep_i]
            if bar.high <= swing_high or bar.close >= swing_high:
                continue
            if bar.high - swing_high < MIN_SWEEP_ATR_FRACTION * atr_value:
                continue
            choch_slice = window[sweep_i + 1:sweep_i + 1 + CHOCH_LOOKBACK]
            if not choch_slice:
                continue
            _, swing_low = _recent_pivot_level(window, lows, sweep_i, kind="low")
            if swing_low is None:
                continue
            choch_i = _choch_bar_index(
                choch_slice, sweep_i, lambda c: c.close < swing_low,
            )
            if choch_i is None or last_i - choch_i > MAX_BARS_SINCE_CHOCH:
                continue

            fvg = find_bearish_fvg(window, max(sweep_i + 1, choch_i - 2), last_i)
            if fvg is None:
                continue
            fvg_i, gap_bottom, gap_top = fvg
            retest_i = _retest_bearish(window, fvg_i, gap_bottom, gap_top, last_i)
            if retest_i is None or last_i - retest_i > MAX_BARS_SINCE_RETEST:
                continue

            stop = bar.high + ATR_STOP_BUFFER * atr_value
            if stop <= entry or not _risk_ok(entry, stop, atr_value):
                continue
            tp1, tp2, tp3 = take_profits_from_risk(
                entry, stop, "short",
                r1=SUPER_SCALP_TP1_R, r2=SUPER_SCALP_TP2_R, r3=SUPER_SCALP_TP3_R,
            )
            indicators = {
                "strategy": "ict_fvg",
                "structure": "bearish_choch_fvg",
                "sweep_level": swing_high,
                "choch_level": swing_low,
                "sweep_high": bar.high,
                "fvg_bottom": gap_bottom,
                "fvg_top": gap_top,
                "atr": atr_value,
                "tp_r": [SUPER_SCALP_TP1_R, SUPER_SCALP_TP2_R, SUPER_SCALP_TP3_R],
            }
            if htf_trend is not None:
                indicators["htf_trend"] = htf_trend
            return CandidateSetup(
                symbol, "short", entry, stop, tp1, indicators,
                take_profit_2=tp2, take_profit_3=tp3,
            )
        return None

    # Soft HTF preference: try with-trend direction first when known.
    if htf_trend == "down":
        order = (_short_candidate, _long_candidate)
    elif htf_trend == "up":
        order = (_long_candidate, _short_candidate)
    else:
        order = (_long_candidate, _short_candidate)

    for search in order:
        setup = search()
        if setup is not None:
            return setup
    return None
