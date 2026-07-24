from signals.chart.plan import build_chart_plan
from signals.models import Signal
from signals.models import Candle as _Candle


def _signal(indicators, direction="long"):
    return Signal(
        id="s1", symbol="XAUUSD", timeframe="5m", direction=direction,
        entry=2006.8, stop_loss=2001.8, take_profit=2009.3,
        take_profit_2=2011.8, take_profit_3=2014.3, confidence=72,
        rationale="r", indicators=indicators, news_headlines=[], created_at="t",
    )


def _kinds(plan, role):
    return [a for a in plan if a["role"] == role]


def test_plan_always_appends_trade_levels():
    plan = build_chart_plan([], _signal({"strategy": "sr_zone",
                                          "side": "support",
                                          "zone_low": 2000.0, "zone_high": 2003.0,
                                          "touches": 3}))
    assert _kinds(plan, "entry") and _kinds(plan, "stop")
    assert len(_kinds(plan, "target")) == 3  # TP1/TP2/TP3


def test_ict_fvg_plan_has_fvg_zone_and_markers():
    ind = {
        "strategy": "ict_fvg", "fvg_top": 2007.0, "fvg_bottom": 2005.7,
        "fvg_start_time": 190, "choch_level": 2008.0, "choch_time": 200,
        "sweep_level": 2004.5, "sweep_low": 2002.3, "sweep_time": 170,
        "retest_time": 230,
    }
    plan = build_chart_plan([], _signal(ind))
    fvg = _kinds(plan, "fvg")
    assert len(fvg) == 1 and fvg[0]["kind"] == "zone"
    markers = [a for a in plan if a["kind"] == "marker"]
    assert {m["order"] for m in markers} == {1, 2, 3}


def test_ict_smc_plan_has_structure_markers():
    ind = {"strategy": "ict_smc", "choch_level": 101.0, "choch_time": 200,
           "sweep_level": 99.0, "sweep_low": 98.5, "sweep_time": 170}
    plan = build_chart_plan([], _signal(ind))
    markers = [a for a in plan if a["kind"] == "marker"]
    assert {m["order"] for m in markers} == {1, 2}
    assert not [a for a in plan if a["role"] == "fvg"]  # ict_smc draws no FVG


def test_sr_zone_plan_has_full_width_zone():
    ind = {"strategy": "sr_zone", "side": "support", "zone_low": 2000.0,
           "zone_high": 2003.0, "touches": 3}
    plan = build_chart_plan([], _signal(ind))
    zones = [a for a in plan if a["role"] == "sr"]
    assert len(zones) == 1
    assert zones[0]["start_time"] is None  # full chart width
    assert "support" in zones[0]["label"]


def test_ema_cross_plan_has_ema_series():
    candles = [_Candle(open_time=i, open=100, high=101, low=99, close=100 + i * 0.1,
                       volume=1.0) for i in range(30)]
    ind = {"ema9": 101.0, "ema21": 100.0, "rsi": 55.0, "macd_hist": 0.2,
           "cross_time": candles[25].open_time}
    plan = build_chart_plan(candles, _signal(ind))
    series_roles = {a["role"] for a in plan if a["kind"] == "series"}
    assert series_roles == {"ema-fast", "ema-slow"}
    assert any(a["kind"] == "marker" and a["time"] == candles[25].open_time for a in plan)
