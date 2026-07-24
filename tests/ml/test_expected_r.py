import pytest

from signals.ml.exceptions import InferenceError
from signals.ml.expected_r import calculate_expected_r


def test_calculate_expected_r_includes_costs():
    probabilities = {
        "sl_before_tp1": 0.20,
        "tp1_then_sl": 0.20,
        "tp2_then_sl": 0.20,
        "tp3_hit": 0.30,
        "expired": 0.10,
    }

    # Weighted gross R = .2(-1) + .2(0) + .2(1) + .3(3) + .1(0) = .90.
    # Net of the configured .05R execution estimate, expected R is .85R.
    assert calculate_expected_r(probabilities, estimated_cost_r=0.05) == pytest.approx(0.85)


def test_calculate_expected_r_rejects_invalid_probabilities():
    probabilities = {
        "sl_before_tp1": 0.20,
        "tp1_then_sl": 0.20,
        "tp2_then_sl": 0.20,
        "tp3_hit": 0.20,
        "expired": 0.10,
    }
    with pytest.raises(InferenceError, match="sum to 1"):
        calculate_expected_r(probabilities)
