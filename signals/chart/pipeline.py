"""Attaches a rendered chart to a signal. Never raises: a chart failure must
never cost a signal, so any error falls back to a text-only (chart_url=None)
signal."""
import dataclasses

from signals.chart.mt5_plan import flatten_plan_for_mt5
from signals.chart.plan import build_chart_plan
from signals.chart.render import render_chart
from signals.chart.upload import upload_chart

SNAPSHOT_BARS = 60


def _snapshot(candles):
    return [
        {"t": c.open_time, "o": c.open, "h": c.high, "l": c.low, "c": c.close}
        for c in candles[-SNAPSHOT_BARS:]
    ]


def attach_chart(signal, candles, *, supabase_url, service_key, session=None,
                 h1_candles=None):
    """Return a copy of `signal` with chart_url + chart_data set, or the
    original signal unchanged if rendering/upload fails."""
    try:
        plan = build_chart_plan(candles, signal, h1_candles=h1_candles)
        png = render_chart(candles, plan, signal)
        url = upload_chart(png, signal.id, supabase_url, service_key, session=session)
        return dataclasses.replace(
            signal, chart_url=url,
            chart_data={"plan": plan, "candles": _snapshot(candles)},
        )
    except Exception as exc:  # noqa: BLE001 - deliberately broad; charts are best-effort
        print(f"[{signal.symbol}] chart render/upload failed "
              f"({type(exc).__name__}: {exc}), sending text-only")
        return signal


def attach_chart_plan(signal, candles, *, h1_candles=None):
    """Gold / MT5 path: store plan + flatten draw fields, leave chart_url null.

    TickPush polls pending setups, draws from flat indicators (including the
    moving cloud CSV series), then ChartScreenShot uploads the real terminal.
    Never raises — a plan failure must not block signal storage.
    """
    try:
        plan = build_chart_plan(candles, signal, h1_candles=h1_candles)
        mt5_fields = flatten_plan_for_mt5(plan, candles, signal)
        ind = dict(signal.indicators or {})
        ind.update(mt5_fields)
        return dataclasses.replace(
            signal,
            indicators=ind,
            chart_url=None,
            chart_data={"plan": plan, "candles": _snapshot(candles)},
        )
    except Exception as exc:  # noqa: BLE001 - best-effort; signal still publishes
        print(f"[{signal.symbol}] MT5 chart plan failed "
              f"({type(exc).__name__}: {exc}), pending will use scalars only")
        return signal
