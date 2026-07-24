from ml.replay.candidate_builder import build_candidate


def test_builder_uses_closed_candle_decision_time_and_reason(long_setup):
    candidate = build_candidate(
        long_setup,
        candidate_timestamp="2024-01-02T00:05:00+00:00",
        source_candle_timestamp="2024-01-02T00:00:00+00:00",
        timeframe="M5", strategy_name="ict_fvg",
        strategy_version="sha256:fixture", dataset_id="dataset-fixture",
        dataset_checksum="abc123", replay_config_version="replay_v1",
        source_commit=None,
    )
    assert candidate.candidate_timestamp == "2024-01-02T00:05:00+00:00"
    assert candidate.signal_reason == "bullish_choch_fvg"
    assert candidate.created_at == candidate.candidate_timestamp

