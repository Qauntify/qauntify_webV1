"""Expected-R calculation shared by model evaluation and live inference."""
from __future__ import annotations

import math
from typing import Mapping

from signals.ml.exceptions import InferenceError


OUTCOME_LABELS = (
    "sl_before_tp1",
    "tp1_then_sl",
    "tp2_then_sl",
    "tp3_hit",
    "expired",
)

DEFAULT_OUTCOME_R = {
    "sl_before_tp1": -1.0,
    "tp1_then_sl": 0.0,
    "tp2_then_sl": 1.0,
    "tp3_hit": 3.0,
    "expired": 0.0,
}


def calculate_expected_r(
    probabilities: Mapping[str, float],
    *,
    outcome_r: Mapping[str, float] = DEFAULT_OUTCOME_R,
    estimated_cost_r: float = 0.0,
    tolerance: float = 1e-6,
) -> float:
    """Return probability-weighted R after estimated execution costs."""
    if tuple(probabilities) != OUTCOME_LABELS:
        raise InferenceError(
            f"Outcome labels/order must be {OUTCOME_LABELS!r}, "
            f"got {tuple(probabilities)!r}"
        )
    if set(outcome_r) != set(OUTCOME_LABELS):
        raise InferenceError("Outcome-R mapping does not match the label set")
    if estimated_cost_r < 0 or not math.isfinite(estimated_cost_r):
        raise InferenceError("estimated_cost_r must be finite and non-negative")

    values = tuple(float(probabilities[label]) for label in OUTCOME_LABELS)
    if any(not math.isfinite(value) or value < 0 or value > 1 for value in values):
        raise InferenceError("Probabilities must be finite values between 0 and 1")
    if not math.isclose(sum(values), 1.0, abs_tol=tolerance):
        raise InferenceError("Probabilities must sum to 1")

    return sum(
        probabilities[label] * float(outcome_r[label]) for label in OUTCOME_LABELS
    ) - estimated_cost_r
