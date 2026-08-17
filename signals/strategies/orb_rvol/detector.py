"""Session Opening Range Breakout on Relative Volume.

Trade the first breakout beyond a session's opening range, in the direction
the range itself moved, but only when that range traded on abnormally high
volume relative to the same session anchor's own recent history. See
docs/superpowers/specs/2026-07-26-orb-rvol-strategy-design.md.

htf_trend/adx are recorded in indicators but never gate — the opening range
IS the directional thesis (see the spec's "Deliberate omissions").
"""
from signals.models import CandidateSetup, take_profits_from_risk
from signals.strategies.orb_rvol.windows import (
    OR_BARS,
    WINDOW_END_MS,
    current_anchor,
    opening_range,
    relative_volume,
)

MIN_RVOL = 1.0  # paper's threshold — expectancy flips sign here
ATR_STOP_BUFFER = 0.25  # stop distance beyond the OR edge
MAX_STOP_ATR = 2.5  # reject wide stops (matches sr_zone)
MIN_CANDLES = 400  # ~4.2 days of 15m; enough for MIN_RVOL_SAMPLES at every anchor
TP1_R, TP2_R, TP3_R = 2.0, 4.0, 6.0  # wide ladder — the edge depends on runners


def _first_breakout_index(candles, anchor_index, direction, or_high, or_low):
    """Index of the FIRST bar in the trade window that closes beyond the OR
    edge in `direction`, or None if none has yet (or ever will, once the
    window has closed).

    Bounded by wall-clock time (anchor open_time + WINDOW_END_MS), not raw
    bar count, so a gap in the candle feed (a missing bar) can't silently
    shrink or stretch how much real time this scan covers — the same
    principle windows.py's own anchor-matching applies. windows.py owns the
    time arithmetic (WINDOW_END_MS); this just walks forward until it runs
    out of window or out of candles.
    """
    anchor_time = candles[anchor_index].open_time
    start = anchor_index + OR_BARS
    for i in range(start, len(candles)):
        bar = candles[i]
        if bar.open_time - anchor_time >= WINDOW_END_MS:
            break
        if direction == "long" and bar.close > or_high:
            return i
        if direction == "short" and bar.close < or_low:
            return i
    return None


def _indicators(session, or_high, or_low, or_direction, rvol, atr_value,
                anchor_time, adx14, htf_trend):
    out = {
        "strategy": "orb_rvol",
        "session": session,
        "or_high": or_high,
        "or_low": or_low,
        "or_direction": or_direction,
        "rvol": rvol,
        "atr": atr_value,
        "anchor_time": anchor_time,
    }
    if adx14 is not None and adx14[-1] is not None:
        out["adx"] = adx14[-1]
    if htf_trend is not None:
        out["htf_trend"] = htf_trend
    return out


def detect_setup(symbol, candles, atr14, adx14=None, htf_trend=None):
    """Return a CandidateSetup on a confirmed opening-range breakout, else None."""
    if len(candles) < MIN_CANDLES or atr14[-1] is None:
        return None
    atr_value = atr14[-1]
    if atr_value <= 0:
        return None

    session, anchor_index = current_anchor(candles)
    if session is None:
        return None

    rng = opening_range(candles, anchor_index)
    if rng is None:
        return None
    or_high, or_low, or_direction = rng
    if or_direction is None:  # doji
        return None

    rvol = relative_volume(candles, session, anchor_index)
    if rvol is None or rvol < MIN_RVOL:
        return None

    direction = "long" if or_direction == "bullish" else "short"
    breakout_index = _first_breakout_index(
        candles, anchor_index, direction, or_high, or_low,
    )
    if breakout_index is None or breakout_index != len(candles) - 1:
        # No breakout yet, or the first one already happened on an earlier
        # bar — one trade per anchor, re-derived statelessly every call.
        return None

    bar = candles[breakout_index]
    entry = bar.close
    if direction == "long":
        stop = or_low - ATR_STOP_BUFFER * atr_value
        if stop >= entry:
            return None
    else:
        stop = or_high + ATR_STOP_BUFFER * atr_value
        if stop <= entry:
            return None
    if abs(entry - stop) / atr_value > MAX_STOP_ATR:
        return None

    tp1, tp2, tp3 = take_profits_from_risk(
        entry, stop, direction, r1=TP1_R, r2=TP2_R, r3=TP3_R,
    )
    return CandidateSetup(
        symbol, direction, entry, stop, tp1,
        _indicators(session, or_high, or_low, or_direction, rvol, atr_value,
                   candles[anchor_index].open_time, adx14, htf_trend),
        take_profit_2=tp2, take_profit_3=tp3,
    )
