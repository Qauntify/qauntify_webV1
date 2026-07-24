"""Normalized drawable primitives shared by every strategy's chart plan.

Each primitive is a plain JSON-serializable dict so the whole plan can be
stored in the signal's `chart_data` column and re-rendered later.
`role` is a semantic tag (e.g. "fvg", "liquidity", "entry") that the renderer
maps to a brand color — builders never choose colors.
"""


def zone(price_top, price_bottom, start_time, label, role):
    """A shaded box (FVG, S/R zone). start_time=None means full chart width."""
    return {
        "kind": "zone",
        "price_top": price_top,
        "price_bottom": price_bottom,
        "start_time": start_time,
        "label": label,
        "role": role,
    }


def level(price, label, role, style="solid", start_time=None):
    """A horizontal line (CHoCH, swept level, entry/SL/TP)."""
    return {
        "kind": "level",
        "price": price,
        "label": label,
        "role": role,
        "style": style,
        "start_time": start_time,
    }


def marker(time, price, label, role, order=None):
    """A labeled dot on a specific candle (sweep, CHoCH confirmation, retest)."""
    return {
        "kind": "marker",
        "time": time,
        "price": price,
        "label": label,
        "role": role,
        "order": order,
    }


def series(points, label, role):
    """A line over the candles (EMA, LWMA). points: [{time, value}, ...]."""
    return {"kind": "series", "points": points, "label": label, "role": role}
