import pandas as pd
import pytest

from ml.training_dataset.v3_builder import (
    assign_primary_splits,
    assign_walk_forward,
    load_model_partition,
    strict_join,
)


FEATURES = ["atr_14"]


def _frames():
    timestamps = pd.to_datetime(["2023-12-31 20:00", "2024-06-01 00:00", "2024-12-31 20:00", "2025-06-01 00:00"])
    features = pd.DataFrame({"candidate_id": list("abcd"), "decision_timestamp": timestamps, "feature_eligible": True, "atr_14": 1.0})
    labels = pd.DataFrame({
        "candidate_id": list("abcd"), "decision_timestamp": timestamps,
        "long_net_profitable": [1, 0, 1, 0], "short_net_profitable": [0, 1, 0, 1],
        "long_net_r_base": [1.0, -1.0, 1.0, -1.0], "short_net_r_base": [-1.0, 1.0, -1.0, 1.0],
        "entry_timestamp": timestamps + pd.Timedelta(minutes=5),
        "long_exit_timestamp": timestamps + pd.Timedelta(hours=1),
        "short_exit_timestamp": timestamps + pd.Timedelta(hours=1),
        "long_result": "TP", "short_result": "SL", "right_censored": False,
        "invalid_reason": None, "supervised_eligible": True,
    })
    return features, labels


def _split():
    return {
        "chronological_split": {
            "validation": {"start_inclusive": "2024-01-01"},
            "untouched_test": {"start_inclusive": "2025-01-01", "end_exclusive": "2026-01-01"},
        },
        "protection": {"embargo_minutes": 240},
        "walk_forward": {"definitions": [{
            "fold": 1, "train_start_inclusive": "2023-01-01",
            "validation_start_inclusive": "2024-01-01", "validation_end_exclusive": "2025-01-01",
        }]},
    }


def test_strict_join_and_targets_are_separate_from_features():
    features, labels = _frames()
    result = strict_join(features, labels, FEATURES)
    assert len(result) == 4 and result.training_eligible.all()
    assert not set(FEATURES) & {"long_net_profitable", "short_net_profitable", "long_net_r_base"}


def test_strict_join_rejects_coverage_mismatch():
    features, labels = _frames()
    with pytest.raises(ValueError, match="coverage mismatch"):
        strict_join(features.iloc[:-1], labels, FEATURES)


def test_primary_split_is_chronological_and_test_locked():
    features, labels = _frames()
    joined = strict_join(features, labels, FEATURES)
    result = assign_primary_splits(joined, _split())
    assert result.set_index("candidate_id").loc["b", "split"] == "validation"
    assert result.set_index("candidate_id").loc["d", "split"] == "untouched_test"
    assert result.loc[result.split == "untouched_test", "test_locked"].all()


def test_purge_uses_actual_outcome_exit_timestamp():
    features, labels = _frames()
    extra_feature = features.iloc[[0]].copy()
    extra_feature["candidate_id"] = "e"
    extra_feature["decision_timestamp"] = pd.Timestamp("2023-06-01")
    extra_label = labels.iloc[[0]].copy()
    extra_label["candidate_id"] = "e"
    extra_label["decision_timestamp"] = pd.Timestamp("2023-06-01")
    extra_label["entry_timestamp"] = pd.Timestamp("2023-06-01 00:05")
    extra_label[["long_exit_timestamp", "short_exit_timestamp"]] = pd.Timestamp("2023-06-01 01:00")
    features = pd.concat([features, extra_feature], ignore_index=True)
    labels = pd.concat([labels, extra_label], ignore_index=True)
    labels.loc[0, ["long_exit_timestamp", "short_exit_timestamp"]] = pd.Timestamp("2024-01-01")
    joined = strict_join(features, labels, FEATURES)
    result = assign_primary_splits(joined, _split())
    assert result.set_index("candidate_id").loc["a", "split"] == "purged"


def test_walk_forward_is_purged_and_chronological():
    features, labels = _frames()
    joined = strict_join(features, labels, FEATURES)
    result = assign_walk_forward(joined, _split())
    assert set(result.role) >= {"train", "validation", "outside"}
    train = result[result.role == "train"]
    assert train.maximum_outcome_exit_timestamp.max() < pd.Timestamp("2024-01-01")


def test_untouched_test_loader_is_locked_by_default(tmp_path):
    with pytest.raises(PermissionError, match="locked"):
        load_model_partition(tmp_path, "untouched_test")
