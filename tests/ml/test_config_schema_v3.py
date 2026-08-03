from copy import deepcopy

import pytest

from ml.config_schema_v3 import (
    DEFAULT_CONFIG_ROOT,
    V3ConfigurationError,
    _canonical_checksum,
    _validate_experiment,
    _validate_label,
    _validate_safeguards,
    _validate_splits,
    load_and_validate_v3_configs,
)

import pathlib

import pytest

# These configs point at ml/data/raw/*.csv, which .gitignore excludes — a
# multi-gigabyte local dataset, not repository content. In CI the file cannot
# exist, so these fail on missing input rather than on anything they were
# written to check. Skip when the data is absent; they run in full for anyone
# who has fetched it.
_M5 = pathlib.Path("ml/data/raw/xauusd_m5_2016_2026.csv")
pytestmark = pytest.mark.skipif(
    not _M5.exists(), reason=f"needs local dataset {_M5} (gitignored)")


def test_repository_v3_configs_are_valid_and_approved():
    bundle = load_and_validate_v3_configs()

    assert bundle.experiment["decision_timeframe"] == "M5"
    assert bundle.experiment["context_timeframes"] == ["M15"]
    assert bundle.label["barriers"]["horizon_bars"] == 48
    assert bundle.ready_for_label_implementation is True
    assert bundle.ready_for_policy_optimization is False
    assert set(bundle.checksums) == {"experiment", "label", "cost", "split", "safeguards"}


def test_config_checksums_are_deterministic():
    first = load_and_validate_v3_configs(DEFAULT_CONFIG_ROOT)
    second = load_and_validate_v3_configs(DEFAULT_CONFIG_ROOT)

    assert first.checksums == second.checksums
    assert _canonical_checksum({"b": 2, "a": 1}) == _canonical_checksum({"a": 1, "b": 2})


def test_experiment_rejects_m1_usage():
    raw = deepcopy(load_and_validate_v3_configs().experiment)
    raw["use_m1_data"] = True

    with pytest.raises(V3ConfigurationError, match="M1 data must be disabled"):
        _validate_experiment(raw)


def test_label_rejects_nonconservative_same_bar_resolution():
    raw = deepcopy(load_and_validate_v3_configs().label)
    raw["ambiguity"]["same_m5_candle_policy"] = "tp_first"

    with pytest.raises(V3ConfigurationError, match="resolve SL first"):
        _validate_label(raw)


def test_split_rejects_test_overlap():
    raw = deepcopy(load_and_validate_v3_configs().split)
    raw["walk_forward"]["definitions"][-1]["validation_end_exclusive"] = "2025-02-01T00:00:00"

    with pytest.raises(V3ConfigurationError, match="reaches or crosses test"):
        _validate_splits(raw)


def test_split_rejects_short_purge():
    raw = deepcopy(load_and_validate_v3_configs().split)
    raw["protection"]["purge_minutes"] = 235

    with pytest.raises(V3ConfigurationError, match="purge must cover"):
        _validate_splits(raw)


def test_safeguards_reject_total_below_fold_requirement():
    raw = deepcopy(load_and_validate_v3_configs().safeguards)
    raw["coverage"]["minimum_total_accepted_candidates"] = 499

    with pytest.raises(V3ConfigurationError, match="fold minimum total"):
        _validate_safeguards(raw)
