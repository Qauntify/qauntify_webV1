"""BBMA Re-entry — trend continuation off the MA5/MA10 pullback.

The setup BBMA sources unanimously call the safest: after a momentum leg, price
pulls back into the MA5/MA10 zone and holds it. For a buy, the bar's low dips
below MA5-Low while its close stays above MA10-High, and the close must not
pass back through the MA10 / Mid BB confluence.

Rule 2 (Mid BB rising) stands in for BBMA's "vertical vs horizontal band"
distinction. The alternative — a bandwidth-expansion threshold — would need a
number no source specifies, so it would be fitted to whatever data we tested it
on. Mid-BB slope captures the same direction with no free parameter, reusing a
lookback the rules already have.
"""
from signals.models import CandidateSetup, take_profits_from_risk
from signals.strategies.bbma.stack import (
    MIN_CANDLES,
    STOP_ATR_BUFFER,
    bbma_stack,
    risk_ok,
    stack_ready,
)

# How far back the momentum leg may sit, and the span the Mid BB slope is
# measured over.
MOMENTUM_LOOKBACK = 10


def _indicators(side, stack, atr_value, adx14, htf_trend):
    out = {
        "strategy": "bbma_reentry",
        "side": side,
        "bb_upper": stack["upper"][-1],
        "bb_mid": stack["mid"][-1],
        "bb_lower": stack["lower"][-1],
        "ma5h": stack["ma5h"][-1],
        "ma5l": stack["ma5l"][-1],
        "ma10h": stack["ma10h"][-1],
        "ma10l": stack["ma10l"][-1],
        "ema50": stack["ema50"][-1],
        "atr": atr_value,
    }
    if adx14 is not None and adx14[-1] is not None:
        out["adx"] = adx14[-1]
    if htf_trend is not None:
        out["htf_trend"] = htf_trend
    return out


def _closed_outside(candles, band, window, above):
    """True when any bar of `window` closed beyond its band value."""
    for i in window:
        level = band[i]
        if level is None:
            continue
        if (candles[i].close > level) if above else (candles[i].close < level):
            return True
    return False


def detect_setup(symbol, candles, atr14, adx14=None, htf_trend=None):
    """Return a CandidateSetup on a BBMA Re-entry pullback, else None.

    `htf_trend` IS gated here — unlike Extreme, this is a with-trend trade, so
    a long against a "down" higher timeframe is refused.
    """
    if len(candles) < MIN_CANDLES or atr14[-1] is None:
        return None
    atr_value = atr14[-1]
    if atr_value <= 0:
        return None

    stack = bbma_stack(candles)
    if not stack_ready(stack):
        return None

    n = len(candles)
    mid_then = stack["mid"][n - MOMENTUM_LOOKBACK]
    if mid_then is None:
        return None

    bar = candles[-1]
    mid, ema50 = stack["mid"][-1], stack["ema50"][-1]
    ma5h, ma5l = stack["ma5h"][-1], stack["ma5l"][-1]
    ma10h, ma10l = stack["ma10h"][-1], stack["ma10l"][-1]
    # Excludes the current bar: that bar is the pullback, and a bar closing
    # outside the band is the momentum candle rather than a re-entry into one.
    leg = range(n - MOMENTUM_LOOKBACK, n - 1)

    if (htf_trend != "down"
            and _closed_outside(candles, stack["upper"], leg, above=True)
            and mid > mid_then
            and bar.close > ema50
            and bar.low <= ma5l
            and bar.close >= ma10h
            and bar.close > mid):
        stop = min(bar.low, ma10l) - STOP_ATR_BUFFER * atr_value
        if stop < bar.close and risk_ok(bar.close, stop, atr_value):
            tp1, tp2, tp3 = take_profits_from_risk(bar.close, stop, "long")
            return CandidateSetup(
                symbol, "long", bar.close, stop, tp1,
                _indicators("support", stack, atr_value, adx14, htf_trend),
                take_profit_2=tp2, take_profit_3=tp3,
            )

    if (htf_trend != "up"
            and _closed_outside(candles, stack["lower"], leg, above=False)
            and mid < mid_then
            and bar.close < ema50
            and bar.high >= ma5h
            and bar.close <= ma10l
            and bar.close < mid):
        stop = max(bar.high, ma10h) + STOP_ATR_BUFFER * atr_value
        if stop > bar.close and risk_ok(bar.close, stop, atr_value):
            tp1, tp2, tp3 = take_profits_from_risk(bar.close, stop, "short")
            return CandidateSetup(
                symbol, "short", bar.close, stop, tp1,
                _indicators("resistance", stack, atr_value, adx14, htf_trend),
                take_profit_2=tp2, take_profit_3=tp3,
            )

    return None
