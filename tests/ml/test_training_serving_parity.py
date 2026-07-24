from ml.features import build_candidate_features as build_offline_features
from signals.ml.features import CandidateFeatureInput
from signals.ml.features import build_candidate_features as build_live_features


def test_training_and_serving_feature_generation_are_identical():
    candidate = CandidateFeatureInput(
        symbol="XAUUSD",
        timeframe="15m",
        session="scalp",
        strategy="sr_zone",
        direction="short",
        entry=2400.0,
        stop_loss=2410.0,
        take_profit_1=2390.0,
        take_profit_2=2380.0,
        take_profit_3=2370.0,
        indicators={"rsi": 48.5, "confirmed": True, "regime": "range"},
    )

    offline = build_offline_features(candidate)
    live = build_live_features(candidate)

    assert offline == live
    assert tuple(offline) == tuple(live)
    assert tuple(type(value) for value in offline.values()) == tuple(
        type(value) for value in live.values()
    )
