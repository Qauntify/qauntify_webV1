"""BBMA Extreme — mean reversion off a Bollinger Band escape.

Rules follow docs/strategy_doc. Manual p23, "Features Extrem": MA5 outside the
band, a reverse candle, then a retest candle which is the entry.

The setup: MA5 (linear weighted, on highs for a sell / lows for a buy) escapes
outside the band, then price rejects back inside. BBMA treats this as an early
reversal signal and explicitly as a scalp.

The first target is structural and mandatory (manual p24, "TP MANDATORY"): a
sell takes profit on the opposite — Low-applied — MA5/MA10, a buy on the
High-applied pair. Because that level sits close to price while the stop sits
beyond the whole spike, Extreme's first target is normally inside 1R. That is
the manual's intent, not a defect: profit is taken early precisely because
direction is not yet confirmed. TP2/TP3 extend one and two R past it so the
engine still has its three-level ladder.

There is deliberately NO band-expansion test. BBMA invalidates an Extreme when
the candle closes OUTSIDE an expanding band (that is momentum, not exhaustion)
and validates it when the candle closes back inside. Requiring the close back
inside therefore excludes the momentum case by construction — no invented
bandwidth threshold, and nothing to overfit.
"""
from signals.models import CandidateSetup
from signals.strategies.bbma.stack import (
    MIN_CANDLES,
    STOP_ATR_BUFFER,
    bbma_stack,
    risk_ok,
    stack_ready,
    structural_targets,
)

# How far back the MA may have escaped the band and still count.
EXTREME_LOOKBACK = 6
# Extreme's mandatory target (the opposite MA5/10) sits close to price while
# its stop sits beyond the whole spike, so the first target is normally inside
# 1R. That is the manual's intent — "take profit early, direction is not yet
# confirmed" — so the only requirement here is that the target be beyond entry.
# A 1R floor, as used for Re-entry, removes every Extreme setup.
EXTREME_MIN_R = 0.0


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
        # Manual p24, "TP MANDATORY": a sell entry takes profit on the MA5/MA10
        # of the opposite (buy) side — the Low-applied pair. The nearer of the
        # two is the first level price reaches on the way down.
        target = max(stack["ma5l"][-1], stack["ma10l"][-1])
        if stop > bar.close and risk_ok(bar.close, stop, atr_value):
            tps = structural_targets(bar.close, stop, "short", target,
                                     min_r=EXTREME_MIN_R)
            if tps:
                return CandidateSetup(
                    symbol, "short", bar.close, stop, tps[0],
                    _indicators("upper", stack, atr_value, adx14, htf_trend),
                    take_profit_2=tps[1], take_profit_3=tps[2],
                )

    if (_escaped(stack["ma5l"], stack["lower"], window, above=False)
            and bar.close > stack["lower"][-1]
            and bar.close > bar.open
            and bar.low <= ma5l
            and bar.close > ma5l):
        stop = min(c.low for c in recent) - STOP_ATR_BUFFER * atr_value
        # Mirror of the short: a buy entry takes profit on the High-applied
        # MA5/MA10 pair, nearer level first.
        target = min(stack["ma5h"][-1], stack["ma10h"][-1])
        if stop < bar.close and risk_ok(bar.close, stop, atr_value):
            tps = structural_targets(bar.close, stop, "long", target,
                                     min_r=EXTREME_MIN_R)
            if tps:
                return CandidateSetup(
                    symbol, "long", bar.close, stop, tps[0],
                    _indicators("lower", stack, atr_value, adx14, htf_trend),
                    take_profit_2=tps[1], take_profit_3=tps[2],
                )

    return None
