import signals.chart.outcome_pipeline as op
from signals.models import Candle


def _c(t):
    return Candle(open_time=t, open=1, high=2, low=0, close=1, volume=0.0)


def _row():
    return {"id": "s1", "symbol": "XAUUSD", "timeframe": "5m",
            "direction": "long", "entry": 100.0, "stop_loss": 98.0,
            "take_profit_1": 101.0, "take_profit_2": 102.0, "take_profit_3": 103.0,
            "chart_data": {"candles": [{"t": 0, "o": 1, "h": 2, "l": 0, "c": 1}]}}


def test_attach_outcome_chart_returns_url_on_success(monkeypatch):
    monkeypatch.setattr(op, "build_outcome_plan", lambda *a, **k: [{"kind": "level"}])
    monkeypatch.setattr(op, "render_outcome_chart", lambda *a, **k: b"PNG")
    monkeypatch.setattr(op, "upload_chart",
                        lambda png, sid, url, key, session=None, suffix="": f"http://x/{sid}{suffix}.png")
    got = op.attach_outcome_chart(_row(), "tp3_hit", [_c(1)],
                                  supabase_url="u", service_key="k")
    assert got == "http://x/s1-outcome.png"


def test_attach_outcome_chart_swallows_errors(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("render exploded")
    monkeypatch.setattr(op, "render_outcome_chart", _boom)
    got = op.attach_outcome_chart(_row(), "sl_hit", [_c(1)],
                                  supabase_url="u", service_key="k")
    assert got is None
