"""S/R bounce entered by a RESTING LIMIT at the zone edge, not at market.

Every other detector in this engine enters at the close of a confirmation
candle — a market order, which is always a taker fill. For a bounce off a level
that is backwards: you chase the rejection, paying the worse price and the
higher fee.

This variant rests an order at the zone edge instead. Measured over 2-4 years
of 15m/1h data, pairing each style with the fee tier it can actually achieve
(market = taker ~0.20% round-trip, limit = maker ~0.04%):

    15m  market  -0.359R      1h  market  -0.126R
    15m  limit   -0.052R      1h  limit   +0.065R   <- the only positive one

Hence 1h only. At 15m the tighter R (0.26% of price vs 0.42%) eats the fee
saving and it still loses.

IMPORTANT — what this model does and does not capture. The setup is only
emitted on a bar that has ALREADY traded through the level, so the fill is
realistic in price terms. It still assumes YOU were filled, which ignores queue
position and competition at an obvious level. That residual cannot be measured
from candles at all, which is why this runs as a paper experiment before any
lifecycle work: see docs/superpowers/specs/.
"""
from signals.models import CandidateSetup, take_profits_from_risk
from signals.strategies.ict_smc.detector import pivot_highs, pivot_lows
from signals.strategies.sr_zone.detector import (
    ATR_STOP_BUFFER,
    MAX_STOP_ATR,
    STRUCTURE_LOOKBACK,
    _cluster_zones,
)

MIN_CANDLES = 40


def _indicators(zone, side, atr_value, adx14, htf_trend):
    out = {
        "strategy": "sr_limit",
        "side": side,
        "zone_low": zone["low"],
        "zone_high": zone["high"],
        "touches": zone["touches"],
        "atr": atr_value,
        "entry_style": "limit",
    }
    if adx14 is not None and adx14[-1] is not None:
        out["adx"] = adx14[-1]
    if htf_trend is not None:
        out["htf_trend"] = htf_trend
    return out


def detect_setup(symbol, candles, atr14, adx14=None, htf_trend=None):
    """Return a CandidateSetup filled at a zone edge this bar, else None.

    Zones are built from `candles[:-1]` — bars strictly BEFORE the filling bar —
    so the order could genuinely have been resting there. Using the current bar
    to place the level would be hindsight.
    """
    if len(candles) < MIN_CANDLES or atr14[-1] is None:
        return None
    atr_value = atr14[-1]
    if atr_value <= 0:
        return None

    window = candles[-STRUCTURE_LOOKBACK:]
    prior = window[:-1]
    bar = candles[-1]

    support = _cluster_zones(prior, pivot_lows(prior), "low", atr_value)
    resistance = _cluster_zones(prior, pivot_highs(prior), "high", atr_value)

    # Long: a resting bid at the zone's upper edge, below where the bar opened,
    # that price traded down into.
    longs = [z for z in support if bar.low <= z["high"] < bar.open]
    if longs and htf_trend != "down":
        zone = max(longs, key=lambda z: z["high"])
        # A gap straight through the level fills at the open, not the level.
        entry = min(zone["high"], bar.open)
        stop = zone["low"] - ATR_STOP_BUFFER * atr_value
        if stop < entry and abs(entry - stop) / atr_value <= MAX_STOP_ATR:
            tp1, tp2, tp3 = take_profits_from_risk(entry, stop, "long")
            return CandidateSetup(
                symbol, "long", entry, stop, tp1,
                _indicators(zone, "support", atr_value, adx14, htf_trend),
                take_profit_2=tp2, take_profit_3=tp3,
            )

    shorts = [z for z in resistance if bar.high >= z["low"] > bar.open]
    if shorts and htf_trend != "up":
        zone = min(shorts, key=lambda z: z["low"])
        entry = max(zone["low"], bar.open)
        stop = zone["high"] + ATR_STOP_BUFFER * atr_value
        if stop > entry and abs(entry - stop) / atr_value <= MAX_STOP_ATR:
            tp1, tp2, tp3 = take_profits_from_risk(entry, stop, "short")
            return CandidateSetup(
                symbol, "short", entry, stop, tp1,
                _indicators(zone, "resistance", atr_value, adx14, htf_trend),
                take_profit_2=tp2, take_profit_3=tp3,
            )
    return None
