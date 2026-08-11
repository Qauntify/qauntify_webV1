from signals.chart.outcome_plan import build_outcome_plan
from signals.chart.render import render_outcome_chart, view_for_outcome
from signals.models import Candle

_PNG = b"\x89PNG\r\n\x1a\n"


def _c(t, o, h, l, c):
    return Candle(open_time=t, open=o, high=h, low=l, close=c, volume=0.0)


def _row():
    return {"symbol": "XAUUSD", "timeframe": "5m", "direction": "long",
            "entry": 100.0, "stop_loss": 98.0, "take_profit_1": 101.0,
            "take_profit_2": 102.0, "take_profit_3": 103.0}


def _candles(n=30):
    out = []
    for i in range(n):
        base = 99 + i * 0.15
        out.append(_c(i * 300000, base, base + 0.3, base - 0.3, base + 0.1))
    return out


def test_render_outcome_chart_returns_png():
    candles = _candles()
    plan = build_outcome_plan(_row(), "tp3_hit", candles, candles[5].open_time)
    png = render_outcome_chart(candles, plan, _row(), candles[5].open_time, "tp3_hit")
    assert png[:8] == _PNG and len(png) > 2000


def test_view_for_outcome_keeps_entry_on_long_path():
    candles = _candles(200)
    entry = candles[50].open_time
    view = view_for_outcome(candles, entry, max_bars=100, pre_entry=16)
    assert view[0].open_time <= entry
    assert any(c.open_time == entry for c in view)
    assert len(view) <= 100
    # Path longer than max_bars: keep entry even if that means clipping the
    # far-right post-exit bars (title must still match what the chart shows).
    assert view[-1].open_time < candles[-1].open_time
