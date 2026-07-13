"""Chandelier Exit (H1) + LWMA200 (M15) scalp detector.

Long only on a fresh H1 CE bullish flip while M15 is in discount
(CE trail below LWMA). Short only on a fresh bearish flip in premium.
SL = active CE trail; TP1/TP2/TP3 = 1R/2R/3R.
"""
from signals.indicators import chandelier_exit, lwma
from signals.models import CandidateSetup, TP1_R, TP2_R, TP3_R, take_profits_from_risk

CE_ATR_PERIOD = 22
CE_MULTIPLIER = 4.5
CE_LOOKBACK = 22
LWMA_PERIOD = 200


def _active_trail(long_stop, short_stop, direction, index: int):
    d = direction[index]
    if d == 1:
        return long_stop[index]
    if d == -1:
        return short_stop[index]
    return None


def detect_setup(symbol, m15_candles, h1_candles):
    """Return a CandidateSetup on a fresh H1 CE flip into the matching zone."""
    if len(m15_candles) < LWMA_PERIOD or len(h1_candles) < CE_LOOKBACK + CE_ATR_PERIOD:
        return None

    h1_highs = [c.high for c in h1_candles]
    h1_lows = [c.low for c in h1_candles]
    h1_closes = [c.close for c in h1_candles]
    long_stop, short_stop, direction = chandelier_exit(
        h1_highs, h1_lows, h1_closes,
        period=CE_ATR_PERIOD, multiplier=CE_MULTIPLIER, lookback=CE_LOOKBACK,
    )
    if direction[-1] is None or direction[-2] is None:
        return None
    # Fresh flip only — same-direction continuation does not re-fire.
    if direction[-1] == direction[-2]:
        return None

    m15_closes = [c.close for c in m15_candles]
    ma = lwma(m15_closes, LWMA_PERIOD)
    if ma[-1] is None:
        return None

    trail = _active_trail(long_stop, short_stop, direction, -1)
    if trail is None:
        return None

    zone_discount = trail < ma[-1]
    zone_premium = trail > ma[-1]
    entry = m15_candles[-1].close
    flipped_long = direction[-2] == -1 and direction[-1] == 1
    flipped_short = direction[-2] == 1 and direction[-1] == -1

    indicators = {
        "strategy": "ce_lwma",
        "ce_trail": trail,
        "ce_direction": "up" if direction[-1] == 1 else "down",
        "lwma200": ma[-1],
        "zone": "discount" if zone_discount else ("premium" if zone_premium else "flat"),
        # CE1/CE2 share settings on the chart — expose both as the same trail.
        "ce1": trail,
        "ce2": trail,
    }

    if flipped_long and zone_discount:
        stop = trail
        if stop >= entry:
            return None
        tp1, tp2, tp3 = take_profits_from_risk(entry, stop, "long")
        return CandidateSetup(
            symbol, "long", entry, stop, tp1, indicators,
            take_profit_2=tp2, take_profit_3=tp3,
        )

    if flipped_short and zone_premium:
        stop = trail
        if stop <= entry:
            return None
        tp1, tp2, tp3 = take_profits_from_risk(entry, stop, "short")
        return CandidateSetup(
            symbol, "short", entry, stop, tp1, indicators,
            take_profit_2=tp2, take_profit_3=tp3,
        )

    return None
