"""ICT 5m super-scalp — hot volume mode.

Entry priority:
1. Sweep + CHoCH + FVG retest (classic)
2. Sweep + CHoCH (no FVG)
3. Sweep reclaim alone (close back through the swept level) — volume fallback

No killzone / session-time filter. SL sits just beyond the sweep extreme;
TP1/TP2/TP3 use short R multiples (0.5 / 1.0 / 1.5).
"""
from signals.models import (
    SUPER_SCALP_TP1_R,
    SUPER_SCALP_TP2_R,
    SUPER_SCALP_TP3_R,
    CandidateSetup,
    take_profits_from_risk,
)
from signals.strategies.ict_smc.detector import (
    _choch_bar_index,
    _recent_pivot_level,
    pivot_highs,
    pivot_lows,
)

# Hot volume overrides — deliberately loose vs swing ict_smc.
PIVOT_LEFT = 1
PIVOT_RIGHT = 1
STRUCTURE_LOOKBACK = 80
CHOCH_LOOKBACK = 20
MAX_BARS_SINCE_CHOCH = 20
MIN_SWEEP_ATR_FRACTION = 0.03
ATR_STOP_BUFFER = 0.25
MAX_STOP_ATR = 4.0
MIN_CANDLES = 25
SWEEP_LOOKBACK = 30
MAX_BARS_SINCE_RETEST = 12
# Sweep-reclaim fallback: sweep bar itself must still be relatively fresh.
MAX_BARS_SINCE_SWEEP = 8


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


def _build(symbol, direction, entry, stop, atr_value, indicators, htf_trend):
    if direction == "long":
        if stop >= entry or not _risk_ok(entry, stop, atr_value):
            return None
    else:
        if stop <= entry or not _risk_ok(entry, stop, atr_value):
            return None
    tp1, tp2, tp3 = take_profits_from_risk(
        entry, stop, direction,
        r1=SUPER_SCALP_TP1_R, r2=SUPER_SCALP_TP2_R, r3=SUPER_SCALP_TP3_R,
    )
    indicators = {
        **indicators,
        "strategy": "ict_fvg",
        "atr": atr_value,
        "tp_r": [SUPER_SCALP_TP1_R, SUPER_SCALP_TP2_R, SUPER_SCALP_TP3_R],
    }
    if htf_trend is not None:
        indicators["htf_trend"] = htf_trend
    return CandidateSetup(
        symbol, direction, entry, stop, tp1, indicators,
        take_profit_2=tp2, take_profit_3=tp3,
    )


def detect_setup(symbol, candles, atr14, htf_trend=None):
    """Return a CandidateSetup on the hottest matching 5m structure, else None."""
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

            stop = bar.low - ATR_STOP_BUFFER * atr_value
            _, swing_high = _recent_pivot_level(window, highs, sweep_i, kind="high")
            choch_i = None
            if swing_high is not None:
                choch_slice = window[sweep_i + 1:sweep_i + 1 + CHOCH_LOOKBACK]
                if choch_slice:
                    choch_i = _choch_bar_index(
                        choch_slice, sweep_i, lambda c: c.close > swing_high,
                    )
                    if choch_i is not None and last_i - choch_i > MAX_BARS_SINCE_CHOCH:
                        choch_i = None

            if choch_i is not None:
                fvg = find_bullish_fvg(window, max(sweep_i + 1, choch_i - 2), last_i)
                retest_i = None
                gap_bottom = gap_top = None
                fvg_i = None
                if fvg is not None:
                    fvg_i, gap_bottom, gap_top = fvg
                    retest_i = _retest_bullish(
                        window, fvg_i, gap_bottom, gap_top, last_i,
                    )
                    if (
                        retest_i is not None
                        and last_i - retest_i > MAX_BARS_SINCE_RETEST
                    ):
                        retest_i = None
                indicators = {
                    "structure": (
                        "bullish_choch_fvg" if retest_i is not None
                        else "bullish_choch"
                    ),
                    "sweep_level": swing_low,
                    "choch_level": swing_high,
                    "sweep_low": bar.low,
                    "sweep_time": window[sweep_i].open_time,
                    "choch_time": window[choch_i].open_time,
                }
                # Always store FVG geometry for the chart when a gap exists —
                # retest only adds the entry-path marker / structure label.
                if fvg_i is not None and gap_bottom is not None and gap_top is not None:
                    indicators["fvg_bottom"] = gap_bottom
                    indicators["fvg_top"] = gap_top
                    indicators["fvg_start_time"] = window[max(fvg_i - 2, 0)].open_time
                if retest_i is not None:
                    indicators["retest_time"] = window[retest_i].open_time
                setup = _build(
                    symbol, "long", entry, stop, atr_value, indicators, htf_trend,
                )
                if setup is not None:
                    return setup
                continue

            # Volume fallback: recent sweep reclaim, no CHoCH yet.
            if last_i - sweep_i > MAX_BARS_SINCE_SWEEP:
                continue
            indicators = {
                "structure": "bullish_sweep_reclaim",
                "sweep_level": swing_low,
                "sweep_low": bar.low,
                "sweep_time": window[sweep_i].open_time,
            }
            setup = _build(
                symbol, "long", entry, stop, atr_value, indicators, htf_trend,
            )
            if setup is not None:
                return setup
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

            stop = bar.high + ATR_STOP_BUFFER * atr_value
            _, swing_low = _recent_pivot_level(window, lows, sweep_i, kind="low")
            choch_i = None
            if swing_low is not None:
                choch_slice = window[sweep_i + 1:sweep_i + 1 + CHOCH_LOOKBACK]
                if choch_slice:
                    choch_i = _choch_bar_index(
                        choch_slice, sweep_i, lambda c: c.close < swing_low,
                    )
                    if choch_i is not None and last_i - choch_i > MAX_BARS_SINCE_CHOCH:
                        choch_i = None

            if choch_i is not None:
                fvg = find_bearish_fvg(window, max(sweep_i + 1, choch_i - 2), last_i)
                retest_i = None
                gap_bottom = gap_top = None
                fvg_i = None
                if fvg is not None:
                    fvg_i, gap_bottom, gap_top = fvg
                    retest_i = _retest_bearish(
                        window, fvg_i, gap_bottom, gap_top, last_i,
                    )
                    if (
                        retest_i is not None
                        and last_i - retest_i > MAX_BARS_SINCE_RETEST
                    ):
                        retest_i = None
                indicators = {
                    "structure": (
                        "bearish_choch_fvg" if retest_i is not None
                        else "bearish_choch"
                    ),
                    "sweep_level": swing_high,
                    "choch_level": swing_low,
                    "sweep_high": bar.high,
                    "sweep_time": window[sweep_i].open_time,
                    "choch_time": window[choch_i].open_time,
                }
                if fvg_i is not None and gap_bottom is not None and gap_top is not None:
                    indicators["fvg_bottom"] = gap_bottom
                    indicators["fvg_top"] = gap_top
                    indicators["fvg_start_time"] = window[max(fvg_i - 2, 0)].open_time
                if retest_i is not None:
                    indicators["retest_time"] = window[retest_i].open_time
                setup = _build(
                    symbol, "short", entry, stop, atr_value, indicators, htf_trend,
                )
                if setup is not None:
                    return setup
                continue

            if last_i - sweep_i > MAX_BARS_SINCE_SWEEP:
                continue
            indicators = {
                "structure": "bearish_sweep_reclaim",
                "sweep_level": swing_high,
                "sweep_high": bar.high,
                "sweep_time": window[sweep_i].open_time,
            }
            setup = _build(
                symbol, "short", entry, stop, atr_value, indicators, htf_trend,
            )
            if setup is not None:
                return setup
        return None

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
