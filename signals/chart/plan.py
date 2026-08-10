"""Turns a signal + candle window into a strategy-agnostic list of primitives.

Each strategy builder emits only its *structure* elements; entry/SL/TP levels
are appended by the dispatcher so every plan has them (DRY).
"""
from signals.chart.annotations import band, level, marker, series, zone
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
    out = []
    if "sweep_level" in ind:
        out.append(level(ind["sweep_level"], "Swept liquidity", "liquidity",
                         style="dotted", start_time=ind.get("sweep_time")))
    if "choch_level" in ind:
        out.append(level(ind["choch_level"], "CHoCH level", "choch",
                         style="dashed", start_time=ind.get("choch_time")))
    sweep_px = ind.get("sweep_low") if signal.direction == "long" else ind.get("sweep_high")
    if ind.get("sweep_time") is not None and sweep_px is not None:
        out.append(marker(ind["sweep_time"], sweep_px, "Liquidity sweep", "liquidity", 1))
    if ind.get("choch_time") is not None and "choch_level" in ind:
        out.append(marker(ind["choch_time"], ind["choch_level"], "CHoCH ✓", "choch", 2))
    return out


def _fvg_end_time(candles, start_time):
    """Right edge of the 3-candle FVG: open of candle-3 + one bar period."""
    if start_time is None or not candles or len(candles) < 2:
        return None
    period = candles[-1].open_time - candles[-2].open_time
    if period <= 0:
        return None
    for i, c in enumerate(candles):
        if c.open_time == start_time:
            # candle1 at i → candle3 at i+2; end after that bar
            if i + 2 < len(candles):
                return candles[i + 2].open_time + period
            return start_time + 3 * period
    return start_time + 3 * period


def _ict_fvg(candles, signal):
    ind = signal.indicators
    out = []
    if "fvg_top" in ind and "fvg_bottom" in ind:
        start = ind.get("fvg_start_time")
        end = ind.get("fvg_end_time") or _fvg_end_time(candles, start)
        out.append(zone(ind["fvg_top"], ind["fvg_bottom"], start,
                        "Fair Value Gap", "fvg", end_time=end))
    out.extend(_ict_smc(candles, signal))
    if ind.get("retest_time") is not None:
        out.append(marker(ind["retest_time"], signal.entry,
                          "FVG retest → entry", "entry", 3))
    elif (
        "sweep_reclaim" in str(ind.get("structure", ""))
        and ind.get("sweep_time") is not None
    ):
        out.append(marker(ind["sweep_time"], signal.entry,
                          "Sweep reclaim → entry", "entry", 3))
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


def cloud_series(candles, h1_candles):
    """Per-15m-bar (cloud_low, cloud_high, ce_band) from the 1h Chandelier.

    The cloud is a fill between two MOVING lines, so drawing it as a fixed
    rectangle — which this did until 2026-08-01 — shows a shape the indicator
    never has. Each bar takes the last 1h candle that had CLOSED by its open
    time, the same causality rule the detector and the backtester use, so the
    drawn cloud is the one the setup was actually read against.
    """
    from signals.indicators import chandelier_exit, sma_atr
    from signals.strategies.cloud_mss.detector import (
        CE_ATR_PERIOD, CE_LOOKBACK, CE_MULTIPLIER, MA_PERIOD,
    )

    long_stop, short_stop, direction = chandelier_exit(
        [c.high for c in h1_candles], [c.low for c in h1_candles],
        [c.close for c in h1_candles], period=CE_ATR_PERIOD,
        multiplier=CE_MULTIPLIER, lookback=CE_LOOKBACK, atr_fn=sma_atr,
    )
    ma = lwma([c.close for c in candles], MA_PERIOD)

    htf_ms = 60 * 60_000
    out = []
    j = -1
    for bar, ma_value in zip(candles, ma):
        while (j + 1 < len(h1_candles)
               and h1_candles[j + 1].open_time + htf_ms <= bar.open_time):
            j += 1
        trend = direction[j] if j >= 0 else None
        band = None
        if trend == 1:
            band = long_stop[j]
        elif trend == -1:
            band = short_stop[j]
        if band is None or ma_value is None:
            out.append((bar.open_time, None, None, None))
        else:
            out.append((bar.open_time, min(band, ma_value),
                        max(band, ma_value), band))
    return out


def _cloud_mss(candles, signal, h1_candles=None):
    """The cloud as a band that follows both its boundaries, the MA200 anchor,
    the Chandelier band itself, and the level whose break confirmed entry.

    Without `h1_candles` the Chandelier cannot be recomputed, so it falls back
    to a flat zone at the values recorded on the signal. That fallback is a
    degraded picture, not the indicator — pass the 1h candles where you have
    them.
    """
    ind = signal.indicators
    side = ind.get("side", "cloud")
    role = side if side in ("premium", "discount") else "sr"
    out = []

    if h1_candles:
        rows = cloud_series(candles, h1_candles)
        out.append(band(
            [{"time": t, "upper": hi, "lower": lo} for t, lo, hi, _ in rows],
            f"Cloud ({side})", role))
        out.append(series(
            [{"time": t, "value": ce} for t, _, _, ce in rows],
            "Chandelier (1h)", "trail"))
    else:
        out.append(zone(ind["cloud_high"], ind["cloud_low"], None,
                        f"Cloud ({side})", role))

    closes = [c.close for c in candles]
    out.append(series([{"time": c.open_time, "value": v}
                       for c, v in zip(candles, lwma(closes, 200))],
                      "LWMA200", "lwma"))
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


def build_chart_plan(candles, signal, h1_candles=None):
    """Return the full annotation list for one signal (structure + trade levels).

    `h1_candles` is only used by multi-timeframe strategies, which need the
    higher-timeframe series to draw their structure truthfully. Builders that
    do not take it are called unchanged.
    """
    ind = signal.indicators or {}
    strategy = ind.get("strategy")
    if strategy is None and "ema9" in ind:
        strategy = "ema_cross"  # ema_cross detector omits the "strategy" key
    builder = _BUILDERS.get(strategy, _no_structure)
    if builder is _cloud_mss:
        plan = list(builder(candles, signal, h1_candles=h1_candles))
    else:
        plan = list(builder(candles, signal))
    plan.extend(_trade_levels(signal))
    return plan
