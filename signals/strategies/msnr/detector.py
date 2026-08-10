"""MSNR (Malaysian Support & Resistance) — 1H swing detector.

Zones are drawn from candle *bodies* (open/close), not wick tips. Fresh zones
(untouched by a later body) are preferred. Direction follows the 4H storyline
when available:

  * up   → longs only (support rejection / RBS)
  * down → shorts only (resistance rejection / SBR)
  * None → range — either edge may fire

Entry modes (both enabled):
  1. Rejection at a fresh body zone
  2. Break & retest — RBS (resistance→support) or SBR (support→resistance)
"""
from signals.models import CandidateSetup, take_profits_from_risk
from signals.strategies.ict_smc.detector import pivot_highs, pivot_lows

STRUCTURE_LOOKBACK = 120
MIN_CANDLES = 40
PIVOT_LEFT = 2
PIVOT_RIGHT = 2
# Body-zone clustering width.
ZONE_ATR_FRACTION = 0.45
MIN_ZONE_ATR = 0.08
# Rejection wick must clear this fraction of ATR into/through the zone.
MIN_REJECTION_WICK_ATR = 0.12
MAX_PIERCE_ATR = 0.55
ATR_STOP_BUFFER = 0.45
MAX_STOP_ATR = 3.0
# Break must be a body close beyond the zone, then retest within this many bars.
MAX_BARS_AFTER_BREAK = 12
# Prefer fresh; allow lightly-tested zones only if still clean (≤1 prior touch).
MAX_UNFRESH_TOUCHES = 1


def _body_bounds(candle) -> tuple[float, float]:
    lo = min(candle.open, candle.close)
    hi = max(candle.open, candle.close)
    if hi <= lo:
        # Doji — use a tiny body around close so zones still form.
        pad = abs(candle.close) * 1e-5 or 1e-6
        return candle.close - pad, candle.close + pad
    return lo, hi


def _risk_ok(entry: float, stop: float, atr_value: float) -> bool:
    if atr_value <= 0:
        return False
    return abs(entry - stop) / atr_value <= MAX_STOP_ATR


def _zone_freshness(candles, zone: dict) -> tuple[bool, int]:
    """Return (is_fresh, body_touches_after_create).

    A body touch is any later candle whose open/close range overlaps the zone.
    """
    created = zone["created_i"]
    touches = 0
    for j in range(created + 1, len(candles) - 1):  # exclude signal bar
        blo, bhi = _body_bounds(candles[j])
        if bhi >= zone["low"] and blo <= zone["high"]:
            touches += 1
    return touches == 0, touches


def _cluster_body_zones(candles, pivot_indices, atr_value: float) -> list[dict]:
    """Cluster nearby pivot *bodies* into MSNR zones."""
    if not pivot_indices or atr_value <= 0:
        return []
    width = ZONE_ATR_FRACTION * atr_value
    items = []
    for i in pivot_indices:
        blo, bhi = _body_bounds(candles[i])
        mid = (blo + bhi) / 2.0
        items.append((mid, blo, bhi, i))
    items.sort(key=lambda x: x[0])

    zones: list[dict] = []
    group = [items[0]]
    for item in items[1:]:
        if item[0] - group[-1][0] <= width:
            group.append(item)
        else:
            zones.append(_finalize_zone(group))
            group = [item]
    zones.append(_finalize_zone(group))

    out = []
    for z in zones:
        if (z["high"] - z["low"]) < MIN_ZONE_ATR * atr_value:
            # Expand thin bodies to a minimum tradable thickness.
            mid = (z["high"] + z["low"]) / 2.0
            half = max(MIN_ZONE_ATR * atr_value / 2.0, (z["high"] - z["low"]) / 2.0)
            z["low"], z["high"] = mid - half, mid + half
        fresh, touches = _zone_freshness(candles, z)
        z["fresh"] = fresh
        z["touches"] = touches
        # Keep every clustered zone — RBS/SBR needs broken levels, and the
        # break candle itself often counts as a body touch. Rejection filters
        # for freshness separately.
        out.append(z)
    return out


def _finalize_zone(group: list[tuple]) -> dict:
    lows = [g[1] for g in group]
    highs = [g[2] for g in group]
    created_i = max(g[3] for g in group)
    return {
        "low": min(lows),
        "high": max(highs),
        "created_i": created_i,
        "pivots": len(group),
    }


def _indicators(side: str, zone: dict, atr_value: float, adx14, htf_trend,
                entry_mode: str) -> dict:
    out = {
        "strategy": "msnr",
        "side": side,
        "entry_mode": entry_mode,
        "zone_low": zone["low"],
        "zone_high": zone["high"],
        "zone_fresh": bool(zone.get("fresh")),
        "zone_touches": int(zone.get("touches", 0)),
        "atr": atr_value,
    }
    if zone.get("break_time") is not None:
        out["break_time"] = zone["break_time"]
    if zone.get("retest_time") is not None:
        out["retest_time"] = zone["retest_time"]
    if zone.get("reject_time") is not None:
        out["reject_time"] = zone["reject_time"]
    if adx14 is not None and adx14[-1] is not None:
        out["adx"] = adx14[-1]
    if htf_trend is not None:
        out["htf_trend"] = htf_trend
    return out


def _long_ok(htf_trend) -> bool:
    return htf_trend != "down"


def _short_ok(htf_trend) -> bool:
    return htf_trend != "up"


def _rejection_long(symbol, candles, atr_value, zones, adx14, htf_trend):
    if not _long_ok(htf_trend):
        return None
    bar = candles[-1]
    entry = bar.close
    if entry <= bar.open:
        return None
    lower_wick = min(bar.open, entry) - bar.low
    if lower_wick < MIN_REJECTION_WICK_ATR * atr_value:
        return None
    candidates = [
        z for z in zones
        if z["high"] < entry
        and bar.low <= z["high"]
        and bar.low >= z["low"] - MAX_PIERCE_ATR * atr_value
        and (z.get("fresh") or int(z.get("touches", 0)) <= MAX_UNFRESH_TOUCHES)
    ]
    if not candidates:
        return None
    # Prefer freshest, then nearest support.
    candidates.sort(key=lambda z: (0 if z.get("fresh") else 1, -z["high"]))
    zone = dict(candidates[0])
    zone["reject_time"] = bar.open_time
    stop = zone["low"] - ATR_STOP_BUFFER * atr_value
    if stop >= entry or not _risk_ok(entry, stop, atr_value):
        return None
    tp1, tp2, tp3 = take_profits_from_risk(entry, stop, "long")
    return CandidateSetup(
        symbol, "long", entry, stop, tp1,
        _indicators("support", zone, atr_value, adx14, htf_trend, "rejection"),
        take_profit_2=tp2, take_profit_3=tp3,
    )


def _rejection_short(symbol, candles, atr_value, zones, adx14, htf_trend):
    if not _short_ok(htf_trend):
        return None
    bar = candles[-1]
    entry = bar.close
    if entry >= bar.open:
        return None
    upper_wick = bar.high - max(bar.open, entry)
    if upper_wick < MIN_REJECTION_WICK_ATR * atr_value:
        return None
    candidates = [
        z for z in zones
        if z["low"] > entry
        and bar.high >= z["low"]
        and bar.high <= z["high"] + MAX_PIERCE_ATR * atr_value
        and (z.get("fresh") or int(z.get("touches", 0)) <= MAX_UNFRESH_TOUCHES)
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda z: (0 if z.get("fresh") else 1, z["low"]))
    zone = dict(candidates[0])
    zone["reject_time"] = bar.open_time
    stop = zone["high"] + ATR_STOP_BUFFER * atr_value
    if stop <= entry or not _risk_ok(entry, stop, atr_value):
        return None
    tp1, tp2, tp3 = take_profits_from_risk(entry, stop, "short")
    return CandidateSetup(
        symbol, "short", entry, stop, tp1,
        _indicators("resistance", zone, atr_value, adx14, htf_trend, "rejection"),
        take_profit_2=tp2, take_profit_3=tp3,
    )


def _find_break_up(candles, zone: dict) -> int | None:
    """Newest bar index with a body close above the resistance zone."""
    start = zone["created_i"] + 1
    last = len(candles) - 1
    for i in range(last - 1, start - 1, -1):
        if last - i > MAX_BARS_AFTER_BREAK:
            break
        if candles[i].close > zone["high"] and candles[i].open <= zone["high"]:
            # Body crossed up through / closed above.
            return i
        if candles[i].close > zone["high"] and min(candles[i].open, candles[i].close) > zone["high"]:
            # Already above — accept first close above after creation.
            return i
    # Simpler: any close above zone after creation, newest within window.
    for i in range(last - 1, max(start, last - MAX_BARS_AFTER_BREAK) - 1, -1):
        if candles[i].close > zone["high"]:
            return i
    return None


def _find_break_down(candles, zone: dict) -> int | None:
    start = zone["created_i"] + 1
    last = len(candles) - 1
    for i in range(last - 1, max(start, last - MAX_BARS_AFTER_BREAK) - 1, -1):
        if candles[i].close < zone["low"]:
            return i
    return None


def _rbs_long(symbol, candles, atr_value, resistance_zones, adx14, htf_trend):
    """Resistance broken → retested as support."""
    if not _long_ok(htf_trend):
        return None
    bar = candles[-1]
    entry = bar.close
    if entry <= bar.open:
        return None
    lower_wick = min(bar.open, entry) - bar.low
    if lower_wick < MIN_REJECTION_WICK_ATR * atr_value:
        return None

    for z in sorted(resistance_zones, key=lambda x: -x["high"]):
        br = _find_break_up(candles, z)
        if br is None:
            continue
        # After break, price must have been above; now retesting from above.
        if any(candles[j].close < z["low"] for j in range(br + 1, len(candles) - 1)):
            continue  # failed flip
        if not (bar.low <= z["high"] and bar.low >= z["low"] - MAX_PIERCE_ATR * atr_value):
            continue
        if entry <= z["low"]:
            continue
        zone = dict(z)
        zone["break_time"] = candles[br].open_time
        zone["retest_time"] = bar.open_time
        zone["fresh"] = False
        stop = zone["low"] - ATR_STOP_BUFFER * atr_value
        if stop >= entry or not _risk_ok(entry, stop, atr_value):
            continue
        tp1, tp2, tp3 = take_profits_from_risk(entry, stop, "long")
        return CandidateSetup(
            symbol, "long", entry, stop, tp1,
            _indicators("rbs", zone, atr_value, adx14, htf_trend, "rbs"),
            take_profit_2=tp2, take_profit_3=tp3,
        )
    return None


def _sbr_short(symbol, candles, atr_value, support_zones, adx14, htf_trend):
    """Support broken → retested as resistance."""
    if not _short_ok(htf_trend):
        return None
    bar = candles[-1]
    entry = bar.close
    if entry >= bar.open:
        return None
    upper_wick = bar.high - max(bar.open, entry)
    if upper_wick < MIN_REJECTION_WICK_ATR * atr_value:
        return None

    for z in sorted(support_zones, key=lambda x: x["low"]):
        br = _find_break_down(candles, z)
        if br is None:
            continue
        if any(candles[j].close > z["high"] for j in range(br + 1, len(candles) - 1)):
            continue
        if not (bar.high >= z["low"] and bar.high <= z["high"] + MAX_PIERCE_ATR * atr_value):
            continue
        if entry >= z["high"]:
            continue
        zone = dict(z)
        zone["break_time"] = candles[br].open_time
        zone["retest_time"] = bar.open_time
        zone["fresh"] = False
        stop = zone["high"] + ATR_STOP_BUFFER * atr_value
        if stop <= entry or not _risk_ok(entry, stop, atr_value):
            continue
        tp1, tp2, tp3 = take_profits_from_risk(entry, stop, "short")
        return CandidateSetup(
            symbol, "short", entry, stop, tp1,
            _indicators("sbr", zone, atr_value, adx14, htf_trend, "sbr"),
            take_profit_2=tp2, take_profit_3=tp3,
        )
    return None


def detect_setup(symbol, candles, atr14, adx14=None, htf_trend=None):
    """Return a CandidateSetup for an MSNR rejection or break-retest, else None."""
    if len(candles) < MIN_CANDLES or atr14[-1] is None:
        return None
    atr_value = atr14[-1]
    if atr_value <= 0:
        return None

    window = candles[-STRUCTURE_LOOKBACK:]
    lows = pivot_lows(window, left=PIVOT_LEFT, right=PIVOT_RIGHT)
    highs = pivot_highs(window, left=PIVOT_LEFT, right=PIVOT_RIGHT)
    support_zones = _cluster_body_zones(window, lows, atr_value)
    resistance_zones = _cluster_body_zones(window, highs, atr_value)

    # Priority: fresh rejection first, then break-retest flips.
    setup = _rejection_long(symbol, window, atr_value, support_zones, adx14, htf_trend)
    if setup is not None:
        return setup
    setup = _rejection_short(symbol, window, atr_value, resistance_zones, adx14, htf_trend)
    if setup is not None:
        return setup
    setup = _rbs_long(symbol, window, atr_value, resistance_zones, adx14, htf_trend)
    if setup is not None:
        return setup
    return _sbr_short(symbol, window, atr_value, support_zones, adx14, htf_trend)
