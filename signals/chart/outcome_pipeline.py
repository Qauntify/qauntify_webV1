"""Renders + uploads an outcome chart. Never raises: a chart failure must
never drop or delay the outcome alert."""
from signals.chart.outcome_plan import build_outcome_plan, merge_outcome_candles
from signals.chart.render import render_outcome_chart
from signals.chart.upload import upload_chart


def attach_outcome_chart(signal_row, outcome, window, *, supabase_url,
                         service_key, session=None):
    """Return the uploaded outcome-chart URL, or None if anything fails."""
    try:
        candles, entry_time = merge_outcome_candles(
            signal_row.get("chart_data"), window)
        if not candles or entry_time is None:
            return None
        plan = build_outcome_plan(signal_row, outcome, candles, entry_time)
        png = render_outcome_chart(candles, plan, signal_row, entry_time, outcome)
        return upload_chart(png, signal_row["id"], supabase_url, service_key,
                            session=session, suffix="-outcome")
    except Exception as exc:  # noqa: BLE001 - charts are best-effort
        print(f"[{signal_row.get('symbol')}] outcome chart failed "
              f"({type(exc).__name__}: {exc}), sending text-only")
        return None
