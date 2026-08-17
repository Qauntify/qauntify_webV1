"""orb_rvol must not fall through to the generic EMA/RSI/MACD no-setup
indicators — that would log misleading fields for a strategy that uses
none of them (see cloud_mss's equivalent regression test/comment)."""
from signals.pipeline.scan import _no_setup_indicators


def test_orb_rvol_no_setup_indicators_are_strategy_tagged():
    indicators = _no_setup_indicators(
        "orb_rvol", [2.0] * 5, [25.0] * 5, "up",
        [1.0] * 5, [1.0] * 5, [50.0] * 5, [0.0] * 5,
    )
    assert indicators["strategy"] == "orb_rvol"
    assert indicators["atr"] == 2.0
    assert indicators["adx"] == 25.0
    assert indicators["htf_trend"] == "up"
    assert "ema9" not in indicators
    assert "rsi" not in indicators


def test_orb_rvol_no_setup_indicators_none_while_atr_warms_up():
    assert _no_setup_indicators(
        "orb_rvol", [None], [None], None, [None], [None], [None], [None],
    ) is None
