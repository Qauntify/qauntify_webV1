import pytest

from signals.ml.feature_schema import schema_from_features
from signals.ml.predictor import score_candidate


class FixedModel:
    def predict_proba(self, rows):
        assert rows == [("XAUUSD", 2.0)]
        return [[0.10, 0.10, 0.20, 0.50, 0.10]]


class BrokenModel:
    def predict_proba(self, rows):
        raise RuntimeError("model backend unavailable")


def test_score_candidate_returns_structured_expected_r_decision():
    features = {"symbol": "XAUUSD", "risk": 2.0}
    result = score_candidate(
        model=FixedModel(),
        features=features,
        schema=schema_from_features(features),
        model_name="candidate-outcome",
        model_version="test-v1",
        minimum_expected_r=0.5,
    )

    assert result.accepted is True
    # .10(-1) + .10(1/3) + .20(1) + .50(2) + .10(0) = 1.1333
    assert result.expected_r == pytest.approx(1 + 2 / 15)
    assert result.reason == "expected_r_above_threshold"
    assert result.to_dict()["probabilities"]["tp3_hit"] == 0.5


def test_score_candidate_abstains_on_schema_failure():
    expected = {"symbol": "XAUUSD", "risk": 2.0}
    result = score_candidate(
        model=FixedModel(),
        features={"risk": 2.0, "symbol": "XAUUSD"},
        schema=schema_from_features(expected),
        model_name="candidate-outcome",
        model_version="test-v1",
        minimum_expected_r=0.0,
    )

    assert result.accepted is False
    assert result.reason == "abstain:FeatureSchemaError"


def test_score_candidate_abstains_on_model_backend_failure():
    features = {"symbol": "XAUUSD", "risk": 2.0}
    result = score_candidate(
        model=BrokenModel(),
        features=features,
        schema=schema_from_features(features),
        model_name="candidate-outcome",
        model_version="test-v1",
        minimum_expected_r=0.0,
    )

    assert result.accepted is False
    assert result.reason == "abstain:InferenceError"
