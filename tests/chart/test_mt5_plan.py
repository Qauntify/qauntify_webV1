"""Tests for MT5 chart-plan flattening (cloud CSV + FVG end)."""
from signals.chart.mt5_plan import flatten_plan_for_mt5
from signals.chart.pipeline import attach_chart_plan
from signals.models import Candle, Signal


def _candle(t, o=100.0, h=101.0, l=99.0, c=100.5):
    return Candle(open_time=t, open=o, high=h, low=l, close=c, volume=1)


def _signal(ind, direction="long"):
    return Signal(
        id="s1", symbol="XAUUSD", timeframe="15m", direction=direction,
        entry=100.0, stop_loss=99.0, take_profit=101.0,
        take_profit_2=None, take_profit_3=None, confidence=70,
        rationale="r", indicators=ind, news_headlines=[], created_at="t",
    )


def test_flatten_cloud_band_to_csv():
    plan = [{
        "kind": "band",
        "label": "Cloud (discount)",
        "role": "discount",
        "points": [
            {"time": 1_700_000_000_000, "upper": 10.0, "lower": 8.0},
            {"time": 1_700_000_900_000, "upper": 11.0, "lower": 9.0},
            {"time": 1_700_001_800_000, "upper": 12.0, "lower": 10.0},
        ],
    }]
    out = flatten_plan_for_mt5(plan, [], _signal({"strategy": "cloud_mss"}))
    assert out["cloud_t"] == "1700000000,1700000900,1700001800"
    assert out["cloud_lo"].startswith("8.00000")
    assert out["cloud_high"] == 12.0
    assert out["cloud_low"] == 10.0


def test_flatten_fvg_end_from_candles():
    # 1m bars; FVG starts at first candle → end after candle-3
    candles = [_candle(1_700_000_000_000 + i * 60_000) for i in range(10)]
    plan = [{
        "kind": "zone", "role": "fvg",
        "price_top": 101, "price_bottom": 100,
        "start_time": candles[0].open_time,
        "end_time": candles[2].open_time + 60_000,
    }]
    ind = {
        "strategy": "ict_fvg",
        "fvg_top": 101, "fvg_bottom": 100,
        "fvg_start_time": candles[0].open_time,
    }
    out = flatten_plan_for_mt5(plan, candles, _signal(ind))
    assert out["fvg_start_time"] == candles[0].open_time
    assert out["fvg_end_time"] == candles[2].open_time + 60_000


def test_attach_chart_plan_sets_data_keeps_url_null(monkeypatch):
    import signals.chart.pipeline as pipeline

    monkeypatch.setattr(
        pipeline, "build_chart_plan",
        lambda c, s, h1_candles=None: [{
            "kind": "band", "role": "premium", "label": "Cloud (premium)",
            "points": [
                {"time": 1000, "upper": 2.0, "lower": 1.0},
                {"time": 2000, "upper": 3.0, "lower": 1.5},
            ],
        }],
    )
    out = attach_chart_plan(_signal({"strategy": "cloud_mss", "side": "premium"}), [])
    assert out.chart_url is None
    assert out.chart_data is not None
    assert "cloud_t" in out.indicators
    assert out.indicators["cloud_high"] == 3.0
