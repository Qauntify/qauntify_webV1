import signals.chart.pipeline as pipeline
from signals.models import Signal


def _signal():
    return Signal(id="s1", symbol="XAUUSD", timeframe="5m", direction="long",
                  entry=100.0, stop_loss=99.0, take_profit=101.0,
                  take_profit_2=None, take_profit_3=None, confidence=70,
                  rationale="r", indicators={"strategy": "ict_fvg"},
                  news_headlines=[], created_at="t")


def test_attach_chart_sets_url_on_success(monkeypatch):
    monkeypatch.setattr(pipeline, "build_chart_plan", lambda c, s: [{"kind": "level"}])
    monkeypatch.setattr(pipeline, "render_chart", lambda c, p, s: b"PNG")
    monkeypatch.setattr(pipeline, "upload_chart",
                        lambda png, sid, url, key, session=None: "http://x/s1.png")
    out = pipeline.attach_chart(_signal(), [], supabase_url="u", service_key="k")
    assert out.chart_url == "http://x/s1.png"
    assert out.chart_data["plan"] == [{"kind": "level"}]


def test_attach_chart_swallows_errors(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("render exploded")
    monkeypatch.setattr(pipeline, "build_chart_plan", lambda c, s: [])
    monkeypatch.setattr(pipeline, "render_chart", _boom)
    out = pipeline.attach_chart(_signal(), [], supabase_url="u", service_key="k")
    assert out.chart_url is None  # signal survives, text-only
