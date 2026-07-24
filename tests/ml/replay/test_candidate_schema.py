from dataclasses import replace

import pytest

from ml.replay.candidate_builder import build_candidate
from ml.replay.candidate_schema import (
    CandidateValidationError,
    validate_candidate,
    validate_candidates,
)


def _build(setup):
    return build_candidate(
        setup,
        candidate_timestamp="2024-01-02T00:05:00+00:00",
        source_candle_timestamp="2024-01-02T00:00:00+00:00",
        timeframe="M5",
        strategy_name="ict_fvg",
        strategy_version="sha256:fixture",
        dataset_id="dataset-fixture",
        dataset_checksum="abc123",
        replay_config_version="replay_v1",
        source_commit="commit-fixture",
    )


def test_valid_long_and_short_candidates(long_setup, short_setup):
    long = _build(long_setup)
    short = _build(short_setup)
    validate_candidate(long)
    validate_candidate(short)
    assert long.risk_reward_tp3 == 3.0
    assert short.risk_reward_tp3 == 3.0


def test_candidate_id_is_deterministic(long_setup):
    assert _build(long_setup).candidate_id == _build(long_setup).candidate_id


def test_invalid_geometry_and_future_fields_fail(long_setup):
    candidate = _build(long_setup)
    with pytest.raises(CandidateValidationError, match="geometry"):
        validate_candidate(replace(candidate, stop_loss=2001.0))
    row = candidate.to_dict() | {"outcome": "win"}
    with pytest.raises(CandidateValidationError, match="Future-derived"):
        validate_candidate(row)


def test_duplicate_and_conflicting_candidate_ids_fail(long_setup):
    candidate = _build(long_setup)
    with pytest.raises(CandidateValidationError, match="Duplicate candidate IDs"):
        validate_candidates((candidate, candidate))
    conflict = replace(candidate, signal_reason="different_rule_reason")
    with pytest.raises(CandidateValidationError, match="Conflicting candidates"):
        validate_candidates((candidate, conflict))
