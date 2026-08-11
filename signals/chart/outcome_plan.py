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


def _contiguous_suffix(candles: list[Candle]) -> list[Candle]:
    """Keep only the newest unbroken time chain.

    Outcome charts merge the setup snapshot with a later fetch. If the MT5
    buffer lost middle bars (purge / cold ring), that merge puts a price hole
    on the plot — drop orphaned older clusters instead of drawing the gap.
    """
    if len(candles) < 2:
        return list(candles)
    deltas = [
        candles[i].open_time - candles[i - 1].open_time
        for i in range(1, len(candles))
        if candles[i].open_time > candles[i - 1].open_time
    ]
    if not deltas:
        return list(candles)
    deltas.sort()
    typical = deltas[len(deltas) // 2]
    # Allow one missed bar; anything wider is a real hole.
    max_gap = max(typical * 2.5, typical + 1)
    out = [candles[-1]]
    for c in reversed(candles[:-1]):
        gap = out[0].open_time - c.open_time
        if gap <= 0 or gap > max_gap:
            break
        out.insert(0, c)
    return out


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
    merged = _contiguous_suffix(merged)
    if entry_time is not None and merged and entry_time < merged[0].open_time:
        # Snapshot was trimmed away by a hole — pin entry to the first kept bar
        # so the vertical divider still lands on the visible path.
        entry_time = merged[0].open_time
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

    post = [c for c in candles if c.open_time >= entry_time]
    full_win = outcome in ("tp3_hit", "tp_hit")
    # Closed partial wins (status frozen at tp1_hit / tp2_hit) or TP crossed
    # before a later stop still count as a win.
    tp1_time = first_cross(post, tp1, direction, "tp") if tp1 is not None else None
    tp2_time = first_cross(post, tp2, direction, "tp") if tp2 is not None else None
    partial_win = (
        outcome in ("tp1_hit", "tp2_hit")
        or (
            outcome == "sl_hit"
            and (bool(signal_row.get("tp1_hit_at")) or tp1_time is not None)
        )
    )

    # Resolve exit time first so levels/zones stop there instead of running
    # forever across post-trade candles.
    if full_win:
        top = tp3 if tp3 is not None else tp1
        exit_time = first_cross(post, top, direction, "tp") if top is not None else None
    elif partial_win:
        top = tp2 if outcome == "tp2_hit" and tp2 is not None else tp1
        exit_time = (
            first_cross(post, top, direction, "tp") if top is not None else None
        ) or tp1_time
    else:
        top = None
        exit_time = first_cross(post, stop, direction, "sl")
    if exit_time is None and post:
        exit_time = post[-1].open_time

    # Entry + SL always. TPs only when they matter — pure losses used to draw
    # TP3 far off-price and crush the candle scale into a flat strip.
    plan = [
        level(entry, "Entry", "entry", start_time=entry_time, end_time=exit_time),
        level(stop, "SL", "stop", style="dashed",
              start_time=entry_time, end_time=exit_time),
    ]
    if full_win or partial_win:
        show_tps = []
        if tp1 is not None:
            show_tps.append((tp1, "TP1"))
        if (full_win or outcome == "tp2_hit" or tp2_time is not None) and tp2 is not None:
            show_tps.append((tp2, "TP2"))
        if full_win and tp3 is not None:
            show_tps.append((tp3, "TP3"))
        for lvl, lbl in show_tps:
            plan.append(level(lvl, lbl, "target", style="dashed",
                              start_time=entry_time, end_time=exit_time))

    for lvl, lbl in ((tp1, "TP1 ✓"), (tp2, "TP2 ✓")):
        if lvl is None:
            continue
        t = first_cross(post, lvl, direction, "tp")
        if t is not None:
            plan.append(marker(t, lvl, lbl, "target"))

    if full_win:
        hit_lvl = tp3 if tp3 is not None else tp1
        if exit_time is not None and hit_lvl is not None:
            plan.append(marker(exit_time, hit_lvl, "✓ TP3 HIT", "win"))
        plan.append(zone(hit_lvl, entry, entry_time, "Captured move", "win",
                         end_time=exit_time))
    elif partial_win:
        hit_lvl = tp2 if outcome == "tp2_hit" and tp2 is not None else tp1
        tag = "✓ TP2 WIN" if outcome == "tp2_hit" else "✓ TP1 WIN"
        if exit_time is not None and hit_lvl is not None:
            plan.append(marker(exit_time, hit_lvl, tag, "win"))
        if hit_lvl is not None:
            plan.append(zone(hit_lvl, entry, entry_time, "Captured move", "win",
                             end_time=exit_time))
    else:
        if exit_time is not None:
            plan.append(marker(exit_time, stop, "✗ SL HIT", "loss"))
        plan.append(zone(entry, stop, entry_time, "Loss", "loss",
                         end_time=exit_time))

    return plan
