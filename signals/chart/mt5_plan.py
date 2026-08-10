"""Flatten a chart plan into MT5-safe scalar / CSV fields for TickPush.

TickPush cannot parse nested JSON (brace scan + flat extractors), so the
moving cloud band becomes comma-separated series and FVG gets an explicit
end time. Stored on `indicators` at gold save so the pending API stays flat.
"""

MT5_CLOUD_BARS = 60


def _sec(ms_or_sec):
    if ms_or_sec is None:
        return None
    t = int(ms_or_sec)
    return t // 1000 if t > 1_000_000_000_000 else t


def _fmt_price(v):
    return f"{float(v):.5f}"


def flatten_plan_for_mt5(plan, candles, signal):
    """Return indicator keys TickPush can draw without nested JSON."""
    out = {}
    ind = signal.indicators or {}

    # --- FVG span (3-candle gap, not full chart width) ---
    if ind.get("fvg_top") is not None and ind.get("fvg_bottom") is not None:
        start = ind.get("fvg_start_time") or ind.get("fvg_time")
        end = ind.get("fvg_end_time")
        if end is None:
            from signals.chart.plan import _fvg_end_time
            end = _fvg_end_time(candles, start)
        if end is None:
            for prim in plan or []:
                if prim.get("kind") == "zone" and prim.get("role") == "fvg":
                    end = prim.get("end_time")
                    if start is None:
                        start = prim.get("start_time")
                    break
        if start is not None:
            out["fvg_start_time"] = int(start)
        if end is not None:
            out["fvg_end_time"] = int(end)

    # --- Moving cloud band (last N valid points) ---
    for prim in plan or []:
        if prim.get("kind") != "band":
            continue
        role = prim.get("role") or ""
        if role not in ("premium", "discount", "sr"):
            # still accept unlabeled cloud bands from builders
            if "cloud" not in (prim.get("label") or "").lower():
                continue
        pts = []
        for p in prim.get("points") or []:
            up, lo = p.get("upper"), p.get("lower")
            t = p.get("time")
            if t is None or up is None or lo is None:
                continue
            if float(up) <= float(lo):
                continue
            pts.append((t, float(lo), float(up)))
        pts = pts[-MT5_CLOUD_BARS:]
        if len(pts) < 2:
            break
        out["cloud_t"] = ",".join(str(_sec(t)) for t, _, _ in pts)
        out["cloud_lo"] = ",".join(_fmt_price(lo) for _, lo, _ in pts)
        out["cloud_hi"] = ",".join(_fmt_price(hi) for _, _, hi in pts)
        # Keep scalar snapshot as mid-band fallback for older EAs.
        out["cloud_low"] = pts[-1][1]
        out["cloud_high"] = pts[-1][2]
        break

    return out
