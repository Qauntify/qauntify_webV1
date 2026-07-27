"""BBMA Extreme — mean reversion off a Bollinger Band escape.

The setup: MA5 (linear weighted, on highs for a sell / lows for a buy) escapes
outside the band, then price rejects back inside. BBMA treats this as an early
reversal signal and explicitly as a scalp — the doctrine is to take profit
quickly because direction is not yet confirmed, which is why the ladder here is
0.5/1/1.5R rather than the engine's usual 1/2/3R.

There is deliberately NO band-expansion test. BBMA invalidates an Extreme when
the candle closes OUTSIDE an expanding band (that is momentum, not exhaustion)
and validates it when the candle closes back inside. Requiring the close back
inside therefore excludes the momentum case by construction — no invented
bandwidth threshold, and nothing to overfit.
"""
from signals.models import CandidateSetup, take_profits_from_risk
from signals.strategies.bbma.stack import (
    MIN_CANDLES,
    STOP_ATR_BUFFER,
    bbma_stack,
    risk_ok,
    stack_ready,
)

# How far back the MA may have escaped the band and still count.
EXTREME_LOOKBACK = 6
# Scalp ladder — an unconfirmed reversal is banked early.
EXTREME_TP1_R = 0.5
EXTREME_TP2_R = 1.0
EXTREME_TP3_R = 1.5


def _indicators(side, stack, atr_value, adx14, htf_trend):
    out = {
        "strategy": "bbma_extreme",
        "side": side,
        "bb_upper": stack["upper"][-1],
        "bb_mid": stack["mid"][-1],
        "bb_lower": stack["lower"][-1],
        "ma5h": stack["ma5h"][-1],
        "ma5l": stack["ma5l"][-1],
        "atr": atr_value,
    }
    # Recorded, never gated — see detect_setup's docstring.
    if adx14 is not None and adx14[-1] is not None:
        out["adx"] = adx14[-1]
    if htf_trend is not None:
        out["htf_trend"] = htf_trend
    return out


def _escaped(ma_series, band_series, window, above):
    """True when the MA sat outside the band on any bar of `window`."""
    for i in window:
        ma, band = ma_series[i], band_series[i]
        if ma is None or band is None:
            continue
        if (ma > band) if above else (ma < band):
            return True
    return False


def detect_setup(symbol, candles, atr14, adx14=None, htf_trend=None):
    """Return a CandidateSetup on a BBMA Extreme rejection, else None.

    `adx14` and `htf_trend` are RECORDED into the setup's indicators but never
    gated on. Extreme is counter-trend by construction, so a trend filter would
    veto nearly every instance of it; carrying the values instead lets the
    backtest answer afterwards whether such a gate would have helped, rather
    than guessing now. This is deliberate — see the design spec.
    """
    if len(candles) < MIN_CANDLES or atr14[-1] is None:
        return None
    atr_value = atr14[-1]
    if atr_value <= 0:
        return None

    stack = bbma_stack(candles)
    if not stack_ready(stack):
        return None

    bar = candles[-1]
    n = len(candles)
    # Includes the current bar: the rejecting bar may itself still have its MA
    # outside the band.
    window = range(n - EXTREME_LOOKBACK, n)
    recent = candles[-EXTREME_LOOKBACK:]
    ma5h, ma5l = stack["ma5h"][-1], stack["ma5l"][-1]

    if (_escaped(stack["ma5h"], stack["upper"], window, above=True)
            and bar.close < stack["upper"][-1]
            and bar.close < bar.open
            and bar.high >= ma5h
            and bar.close < ma5h):
        stop = max(c.high for c in recent) + STOP_ATR_BUFFER * atr_value
        if stop > bar.close and risk_ok(bar.close, stop, atr_value):
            tp1, tp2, tp3 = take_profits_from_risk(
                bar.close, stop, "short",
                r1=EXTREME_TP1_R, r2=EXTREME_TP2_R, r3=EXTREME_TP3_R,
            )
            return CandidateSetup(
                symbol, "short", bar.close, stop, tp1,
                _indicators("upper", stack, atr_value, adx14, htf_trend),
                take_profit_2=tp2, take_profit_3=tp3,
            )

    if (_escaped(stack["ma5l"], stack["lower"], window, above=False)
            and bar.close > stack["lower"][-1]
            and bar.close > bar.open
            and bar.low <= ma5l
            and bar.close > ma5l):
        stop = min(c.low for c in recent) - STOP_ATR_BUFFER * atr_value
        if stop < bar.close and risk_ok(bar.close, stop, atr_value):
            tp1, tp2, tp3 = take_profits_from_risk(
                bar.close, stop, "long",
                r1=EXTREME_TP1_R, r2=EXTREME_TP2_R, r3=EXTREME_TP3_R,
            )
            return CandidateSetup(
                symbol, "long", bar.close, stop, tp1,
                _indicators("lower", stack, atr_value, adx14, htf_trend),
                take_profit_2=tp2, take_profit_3=tp3,
            )

    return None
