"""Builds the annotation plan + merged candles for an outcome (result) chart."""
from signals.chart.annotations import level, marker, zone
from signals.models import Candle


def first_cross(candles, level_price, direction, kind):
    """open_time of the first candle to cross `level_price`, else None.

    kind "tp": long hits when high >= level, short when low <= level.
    kind "sl": long hits when low <= level, short when high >= level.
    """
    for c in candles:
        if kind == "tp":
            hit = c.high >= level_price if direction == "long" else c.low <= level_price
        else:
            hit = c.low <= level_price if direction == "long" else c.high >= level_price
        if hit:
            return c.open_time
    return None


def _snapshot_candles(chart_data):
    snap = (chart_data or {}).get("candles") or []
    return [Candle(open_time=c["t"], open=c["o"], high=c["h"], low=c["l"],
                   close=c["c"], volume=0.0) for c in snap]


def merge_outcome_candles(chart_data, window):
    """Merge the stored setup snapshot with the price-path `window`.

    Deduped by open_time (window wins collisions) and sorted. Returns
    (candles, entry_time) where entry_time is the last snapshot candle's
    open_time, or the first window candle's when there is no snapshot.
    """
    setup = _snapshot_candles(chart_data)
    by_time = {}
    for c in setup + list(window):
        by_time[c.open_time] = c
    merged = [by_time[t] for t in sorted(by_time)]
    entry_time = setup[-1].open_time if setup else (window[0].open_time if window else None)
    return merged, entry_time


def _tp_levels(row):
    tp1 = row.get("take_profit_1") if row.get("take_profit_1") is not None else row.get("take_profit")
    return (
        float(tp1) if tp1 is not None else None,
        float(row["take_profit_2"]) if row.get("take_profit_2") is not None else None,
        float(row["take_profit_3"]) if row.get("take_profit_3") is not None else None,
    )


def build_outcome_plan(signal_row, outcome, candles, entry_time):
    """Annotation list for an outcome chart: entry/SL/TP levels, per-target ✓
    marks, the HIT/STOP flag, and the captured-move (win) or loss zone."""
    direction = signal_row["direction"]
    entry = float(signal_row["entry"])
    stop = float(signal_row["stop_loss"])
    tp1, tp2, tp3 = _tp_levels(signal_row)

    plan = [level(entry, "Entry", "entry"),
            level(stop, "SL", "stop", style="dashed")]
    for lvl, lbl in ((tp1, "TP1"), (tp2, "TP2"), (tp3, "TP3")):
        if lvl is not None:
            plan.append(level(lvl, lbl, "target", style="dashed"))

    post = [c for c in candles if c.open_time >= entry_time]
    full_win = outcome in ("tp3_hit", "tp_hit")
    # Closed partial wins (status frozen at tp1_hit / tp2_hit) or TP crossed
    # before a later stop still count as a win.
    tp1_time = first_cross(post, tp1, direction, "tp") if tp1 is not None else None
    partial_win = (
        outcome in ("tp1_hit", "tp2_hit")
        or (
            outcome == "sl_hit"
            and (bool(signal_row.get("tp1_hit_at")) or tp1_time is not None)
        )
    )
    win = full_win or partial_win

    for lvl, lbl in ((tp1, "TP1 ✓"), (tp2, "TP2 ✓")):
        if lvl is None:
            continue
        t = first_cross(post, lvl, direction, "tp")
        if t is not None:
            plan.append(marker(t, lvl, lbl, "target"))

    if full_win:
        top = tp3 if tp3 is not None else tp1
        t = first_cross(post, top, direction, "tp")
        if t is not None:
            plan.append(marker(t, top, "✓ TP3 HIT", "win"))
        plan.append(zone(top, entry, entry_time, "Captured move", "win"))
    elif partial_win:
        top = tp2 if outcome == "tp2_hit" and tp2 is not None else tp1
        tag = "✓ TP2 WIN" if outcome == "tp2_hit" else "✓ TP1 WIN"
        t = first_cross(post, top, direction, "tp") if top is not None else None
        if t is not None and top is not None:
            plan.append(marker(t, top, tag, "win"))
        elif tp1_time is not None and tp1 is not None:
            plan.append(marker(tp1_time, tp1, "✓ TP1 WIN", "win"))
        if top is not None:
            plan.append(zone(top, entry, entry_time, "Captured move", "win"))
    else:
        t = first_cross(post, stop, direction, "sl")
        if t is not None:
            plan.append(marker(t, stop, "✗ SL HIT", "loss"))
        plan.append(zone(entry, stop, entry_time, "Loss", "loss"))

    return plan
