"""Support/Resistance bounce: buy at support / sell at resistance, but only
on a confirmation candle (a rejection wick that closes back inside the range).

Horizontal S/R zones are built by clustering swing pivots; a zone needs at
least MIN_TOUCHES pivots to count as a genuine tested level. Unlike the trend
strategies (ema_cross / ict_smc, which require ADX >= 20), a bounce is
mean-reversion — it favours ranging markets, so a strong trend (ADX at/above
ADX_RANGE_MAX) is a veto, not a requirement.
"""
from signals.models import CandidateSetup, take_profits_from_risk
from signals.strategies.ict_smc.detector import pivot_highs, pivot_lows

STRUCTURE_LOOKBACK = 120
MIN_CANDLES = 30
# Pivots within this many ATRs of each other merge into one zone.
ZONE_ATR_FRACTION = 0.5
# A zone must have been tested at least this many times to trade.
MIN_TOUCHES = 2
# The confirmation candle's rejection wick must clear this fraction of ATR —
# a token wick is not a defended level.
MIN_REJECTION_WICK_ATR = 0.12
# Stop sits this many ATRs beyond the zone edge (zones get wick-hunted).
ATR_STOP_BUFFER = 0.5
# The confirmation wick may pierce this many ATRs past the far zone edge and
# still count as a bounce; deeper than that is a break, not a rejection.
MAX_PIERCE_ATR = 0.5
# Reject setups whose stop is farther than this many ATRs from entry.
MAX_STOP_ATR = 2.5
# ADX at/above this marks a strong trend — skip mean-reversion bounces.
ADX_RANGE_MAX = 35.0


def _zone_from_group(group: list[float]) -> dict:
    return {"low": min(group), "high": max(group), "touches": len(group)}


def _cluster_zones(candles, pivot_indices, kind: str, atr_value: float) -> list[dict]:
    """Group nearby pivot prices into zones; keep only tested (>=MIN_TOUCHES) ones.

    `kind` is "low" for support (uses each pivot bar's low) or "high" for
    resistance (uses its high). Single-linkage: prices within
    ZONE_ATR_FRACTION*ATR of the running group extend it.
    """
    prices = sorted(
        candles[i].low if kind == "low" else candles[i].high
        for i in pivot_indices
    )
    if not prices:
        return []
    width = ZONE_ATR_FRACTION * atr_value
    zones: list[dict] = []
    group = [prices[0]]
    for price in prices[1:]:
        if price - group[-1] <= width:
            group.append(price)
        else:
            zones.append(_zone_from_group(group))
            group = [price]
    zones.append(_zone_from_group(group))
    return [z for z in zones if z["touches"] >= MIN_TOUCHES]


def _risk_ok(entry: float, stop: float, atr_value: float) -> bool:
    if atr_value <= 0:
        return False
    return abs(entry - stop) / atr_value <= MAX_STOP_ATR


def _indicators(side: str, zone: dict, atr_value: float, adx14, htf_trend) -> dict:
    indicators = {
        "strategy": "sr_zone",
        "side": side,
        "zone_low": zone["low"],
        "zone_high": zone["high"],
        "touches": zone["touches"],
        "atr": atr_value,
    }
    if adx14 is not None and adx14[-1] is not None:
        indicators["adx"] = adx14[-1]
    if htf_trend is not None:
        indicators["htf_trend"] = htf_trend
    return indicators


def _long_bounce(symbol, bar, atr_value, zones, adx14, htf_trend):
    if htf_trend == "down":
        return None
    entry = bar.close
    if entry <= bar.open:  # need a bullish rejection close
        return None
    lower_wick = min(bar.open, entry) - bar.low
    if lower_wick < MIN_REJECTION_WICK_ATR * atr_value:
        return None
    candidates = [
        z for z in zones
        if z["high"] < entry                                  # zone below the close
        and bar.low <= z["high"]                              # wick reached the zone
        and bar.low >= z["low"] - MAX_PIERCE_ATR * atr_value  # didn't break through
    ]
    if not candidates:
        return None
    zone = max(candidates, key=lambda z: z["high"])  # nearest support below close
    stop = zone["low"] - ATR_STOP_BUFFER * atr_value
    if stop >= entry or not _risk_ok(entry, stop, atr_value):
        return None
    tp1, tp2, tp3 = take_profits_from_risk(entry, stop, "long")
    return CandidateSetup(
        symbol, "long", entry, stop, tp1,
        _indicators("support", zone, atr_value, adx14, htf_trend),
        take_profit_2=tp2, take_profit_3=tp3,
    )


def _short_bounce(symbol, bar, atr_value, zones, adx14, htf_trend):
    if htf_trend == "up":
        return None
    entry = bar.close
    if entry >= bar.open:  # need a bearish rejection close
        return None
    upper_wick = bar.high - max(bar.open, entry)
    if upper_wick < MIN_REJECTION_WICK_ATR * atr_value:
        return None
    candidates = [
        z for z in zones
        if z["low"] > entry                                     # zone above the close
        and bar.high >= z["low"]                                # wick reached the zone
        and bar.high <= z["high"] + MAX_PIERCE_ATR * atr_value  # didn't break through
    ]
    if not candidates:
        return None
    zone = min(candidates, key=lambda z: z["low"])  # nearest resistance above close
    stop = zone["high"] + ATR_STOP_BUFFER * atr_value
    if stop <= entry or not _risk_ok(entry, stop, atr_value):
        return None
    tp1, tp2, tp3 = take_profits_from_risk(entry, stop, "short")
    return CandidateSetup(
        symbol, "short", entry, stop, tp1,
        _indicators("resistance", zone, atr_value, adx14, htf_trend),
        take_profit_2=tp2, take_profit_3=tp3,
    )


def detect_setup(symbol, candles, atr14, adx14=None, htf_trend=None):
    """Return a CandidateSetup on a confirmed S/R bounce, else None.

    `adx14`, when given, vetoes strong trends (ADX >= ADX_RANGE_MAX) where
    levels get run through. `htf_trend` ("up"/"down"), when given, filters the
    direction the same way ema_cross does — no long against a "down" HTF trend,
    no short against an "up" one. Both default to None (filter skipped).
    """
    if len(candles) < MIN_CANDLES or atr14[-1] is None:
        return None
    atr_value = atr14[-1]
    if atr_value <= 0:
        return None
    if adx14 is not None and adx14[-1] is not None and adx14[-1] >= ADX_RANGE_MAX:
        return None

    window = candles[-STRUCTURE_LOOKBACK:]
    support_zones = _cluster_zones(window, pivot_lows(window), "low", atr_value)
    resistance_zones = _cluster_zones(window, pivot_highs(window), "high", atr_value)
    bar = window[-1]

    long_setup = _long_bounce(symbol, bar, atr_value, support_zones, adx14, htf_trend)
    if long_setup is not None:
        return long_setup
    return _short_bounce(symbol, bar, atr_value, resistance_zones, adx14, htf_trend)
