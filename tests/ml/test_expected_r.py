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

    # Weighted gross R = .2(-1) + .2(1/3) + .2(1) + .3(2) + .1(0) ≈ 0.6667.
    # tp3_hit is 2R, not 3R: a scale-out books thirds at 1R/2R/3R, so a full
    # winner realises (1+2+3)/3 = 2R on the whole position.
    # Net of the configured .05R execution estimate ≈ 0.6167R.
    assert calculate_expected_r(probabilities, estimated_cost_r=0.05) == pytest.approx(
        0.2 * (-1) + 0.2 * (1 / 3) + 0.2 * 1 + 0.3 * 2 + 0.1 * 0 - 0.05
    )


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
