"""Turns a signal + candle window into a strategy-agnostic list of primitives.

Each strategy builder emits only its *structure* elements; entry/SL/TP levels
are appended by the dispatcher so every plan has them (DRY).
"""
from signals.chart.annotations import level, marker, series, zone
from signals.indicators import ema, lwma


def _trade_levels(signal):
    out = [
        level(signal.entry, "Entry", "entry"),
        level(signal.stop_loss, "SL", "stop", style="dashed"),
        level(signal.take_profit, "TP1", "target", style="dashed"),
    ]
    if signal.take_profit_2 is not None:
        out.append(level(signal.take_profit_2, "TP2", "target", style="dashed"))
    if signal.take_profit_3 is not None:
        out.append(level(signal.take_profit_3, "TP3", "target", style="dashed"))
    return out


def _ict_smc(candles, signal):
    ind = signal.indicators
    out = [
        level(ind["choch_level"], "CHoCH level", "choch",
              style="dashed", start_time=ind.get("choch_time")),
        level(ind["sweep_level"], "Swept liquidity", "liquidity",
              style="dotted", start_time=ind.get("sweep_time")),
    ]
    sweep_px = ind.get("sweep_low") if signal.direction == "long" else ind.get("sweep_high")
    if ind.get("sweep_time") is not None and sweep_px is not None:
        out.append(marker(ind["sweep_time"], sweep_px, "Liquidity sweep", "liquidity", 1))
    if ind.get("choch_time") is not None:
        out.append(marker(ind["choch_time"], ind["choch_level"], "CHoCH ✓", "choch", 2))
    return out


def _ict_fvg(candles, signal):
    ind = signal.indicators
    out = [zone(ind["fvg_top"], ind["fvg_bottom"], ind.get("fvg_start_time"),
                "Fair Value Gap", "fvg")]
    out.extend(_ict_smc(candles, signal))
    if ind.get("retest_time") is not None:
        out.append(marker(ind["retest_time"], signal.entry,
                          "FVG retest → entry", "entry", 3))
    return out


def _sr_zone(candles, signal):
    ind = signal.indicators
    label = f"{ind.get('side', 'S/R')} zone ({ind.get('touches', '?')}x)"
    return [zone(ind["zone_high"], ind["zone_low"], None, label, "sr")]


def _ema_cross(candles, signal):
    closes = [c.close for c in candles]
    ema9, ema21 = ema(closes, 9), ema(closes, 21)
    pts9 = [{"time": c.open_time, "value": v} for c, v in zip(candles, ema9)]
    pts21 = [{"time": c.open_time, "value": v} for c, v in zip(candles, ema21)]
    out = [series(pts9, "EMA9", "ema-fast"), series(pts21, "EMA21", "ema-slow")]
    ct = signal.indicators.get("cross_time")
    if ct is not None:
        out.append(marker(ct, signal.entry, "EMA cross", "entry", 1))
    return out


def _ce_lwma(candles, signal):
    ind = signal.indicators
    closes = [c.close for c in candles]
    pts = [{"time": c.open_time, "value": v} for c, v in zip(candles, lwma(closes, 200))]
    out = [series(pts, "LWMA200 (premium/discount)", "lwma")]
    if ind.get("ce_trail") is not None:
        out.append(level(ind["ce_trail"], "Chandelier trail", "trail", style="dashed"))
    return out


def _bbma(candles, signal):
    """The full BBMA stack: Bollinger envelope, the MA5/MA10 High-Low pairs and
    EMA50 — the five lines every BBMA setup is read against.

    All eight series are drawn because the setup is defined by their geometry:
    an Extreme is MA5 escaping the band, a Re-entry is price dipping into the
    MA5/MA10 zone and closing back above it. Showing only price would hide the
    reason the setup fired.
    """
    from signals.strategies.bbma.stack import bbma_stack

    stack = bbma_stack(candles)

    def _pts(key):
        return [{"time": c.open_time, "value": v}
                for c, v in zip(candles, stack[key])]

    out = [
        series(_pts("upper"), "BB upper", "bb-band"),
        series(_pts("lower"), "BB lower", "bb-band"),
        series(_pts("mid"), "BB mid", "bb-mid"),
        series(_pts("ma5h"), "MA5 High", "ma5"),
        series(_pts("ma5l"), "MA5 Low", "ma5"),
        series(_pts("ma10h"), "MA10 High", "ma10"),
        series(_pts("ma10l"), "MA10 Low", "ma10"),
        series(_pts("ema50"), "EMA50", "ema50"),
    ]
    if candles:
        label = ("Re-entry → entry"
                 if signal.indicators.get("strategy") == "bbma_reentry"
                 else "Extreme rejection → entry")
        out.append(marker(candles[-1].open_time, signal.entry, label, "entry", 1))
    return out


def _cloud_mss(candles, signal):
    """The cloud as a zone, the MA200 it is anchored to, and the structure
    level whose break confirmed the entry.

    The cloud is drawn in the premium/discount roles rather than a neutral one
    so its side is readable at a glance — that side IS the bias, and a chart
    that hid it would show the trade without its reason.
    """
    ind = signal.indicators
    side = ind.get("side", "cloud")
    out = [
        zone(ind["cloud_high"], ind["cloud_low"], None,
             f"Cloud ({side})", side if side in ("premium", "discount") else "sr"),
    ]
    closes = [c.close for c in candles]
    pts = [{"time": c.open_time, "value": v}
           for c, v in zip(candles, lwma(closes, 200))]
    out.append(series(pts, "LWMA200", "lwma"))
    if ind.get("choch_level") is not None:
        out.append(level(ind["choch_level"], "CHoCH level", "choch",
                         style="dashed"))
    return out


_BUILDERS = {
    "ict_fvg": _ict_fvg,
    "ict_smc": _ict_smc,
    "sr_zone": _sr_zone,
    "ema_cross": _ema_cross,
    "ce_lwma": _ce_lwma,
    "cloud_mss": _cloud_mss,
    "bbma_extreme": _bbma,
    "bbma_reentry": _bbma,
}


def _no_structure(candles, signal):
    return []


def build_chart_plan(candles, signal):
    """Return the full annotation list for one signal (structure + trade levels)."""
    ind = signal.indicators or {}
    strategy = ind.get("strategy")
    if strategy is None and "ema9" in ind:
        strategy = "ema_cross"  # ema_cross detector omits the "strategy" key
    builder = _BUILDERS.get(strategy, _no_structure)
    plan = list(builder(candles, signal))
    plan.extend(_trade_levels(signal))
    return plan
