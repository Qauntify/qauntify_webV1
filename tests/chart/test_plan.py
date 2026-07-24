from signals.chart.plan import build_chart_plan
from signals.models import Signal


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
