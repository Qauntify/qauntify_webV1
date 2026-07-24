import pytest

from signals.ml.exceptions import FeatureSchemaError
from signals.ml.features import CandidateFeatureInput, build_candidate_features


def _candidate(**overrides):
    values = {
        "symbol": "XAUUSD",
        "timeframe": "15m",
        "session": "scalp",
        "strategy": "sr_zone",
        "direction": "long",
        "entry": 2400.0,
        "stop_loss": 2390.0,
        "take_profit_1": 2410.0,
        "take_profit_2": 2420.0,
        "take_profit_3": 2430.0,
        "indicators": {"rsi": 51.0, "adx": 22.0},
    }
    values.update(overrides)
    return CandidateFeatureInput(**values)


def test_build_candidate_features_is_deterministic_and_normalizes_geometry():
    features = build_candidate_features(_candidate())

    assert tuple(features)[-2:] == ("indicator.adx", "indicator.rsi")
    assert features["risk_distance"] == 10.0
    assert features["tp1_r"] == 1.0
    assert features["tp2_r"] == 2.0
    assert features["tp3_r"] == 3.0


def test_build_candidate_features_rejects_zero_risk():
    with pytest.raises(FeatureSchemaError, match="must differ"):
        build_candidate_features(_candidate(stop_loss=2400.0))
