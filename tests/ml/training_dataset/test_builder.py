import json
from types import SimpleNamespace

import pandas as pd
import pytest

from ml.features.schema import BOOLEAN_FEATURES, CATEGORICAL_FEATURES, NUMERIC_FEATURES
from ml.replay.replay_export import _checksum
from ml.training_dataset.builder import BuildResult, chronological_splits, strict_join, walk_forward_splits
from ml.training_dataset.export import export_training


def config(**overrides):
    values = dict(train_fraction=.7, validation_fraction=.15, test_fraction=.15, embargo_days=14,
                  walk_forward_folds=5, walk_initial_fraction=.5, walk_validation_fraction=.1,
                  compression="zstd")
    values.update(overrides)
    return SimpleNamespace(**values)


def inputs(count=1000):
    timestamp = pd.date_range("2020-01-01", periods=count, freq="D", tz="UTC")
    features = pd.DataFrame({"candidate_id": [f"id-{i:04}" for i in range(count)],
        "candidate_timestamp": timestamp, "source_candle_timestamp": timestamp-pd.Timedelta(hours=1),
        "strategy_name": "ema_cross", "timeframe": "H1", "direction": "long"})
    for name in NUMERIC_FEATURES: features[name] = 1.0
    for name in BOOLEAN_FEATURES: features[name] = False
    for name in CATEGORICAL_FEATURES: features[name] = "none"
    outcomes = pd.DataFrame({"candidate_id": features.candidate_id, "outcome_class": "tp3_hit",
        "net_realized_r": 1.0, "resolution_timestamp": timestamp+pd.Timedelta(days=1),
        "holding_seconds": 3600.0, "mfe_r": 2.0, "mae_r": .5, "right_censored": False})
    return features, outcomes


def test_strict_one_to_one_join_and_targets():
    features, outcomes = inputs(100)
    outcomes.loc[0, ["outcome_class", "net_realized_r", "right_censored"]] = ["right_censored", None, True]
    outcomes.loc[1, "net_realized_r"] = 0.0
    result = strict_join(features, outcomes)
    assert len(result) == result.candidate_id.nunique() == 100
    assert pd.isna(result.loc[result.candidate_id == "id-0000", "target_binary_success"]).all()
    assert result.loc[result.candidate_id == "id-0001", "target_binary_success"].iloc[0] == 0
    assert result.loc[result.candidate_id == "id-0002", "target_binary_success"].iloc[0] == 1


def test_join_rejects_missing_and_duplicate_ids():
    features, outcomes = inputs(100)
    with pytest.raises(ValueError, match="coverage mismatch"):
        strict_join(features, outcomes.iloc[:-1])
    with pytest.raises(ValueError, match="Duplicate"):
        strict_join(pd.concat([features, features.iloc[:1]]), outcomes)


def test_chronology_embargo_and_label_window_purge():
    frame = strict_join(*inputs())
    assignments, policy = chronological_splits(frame, config())
    eligible = assignments[assignments.supervised_eligible]
    train = eligible[eligible.split == "train"]; validation = eligible[eligible.split == "validation"]; test = eligible[eligible.split == "test"]
    assert train.candidate_timestamp.max() < validation.candidate_timestamp.min() < test.candidate_timestamp.min()
    assert train.resolution_timestamp.max() < pd.Timestamp(policy["validation_start"])
    assert validation.resolution_timestamp.max() < pd.Timestamp(policy["test_start"])
    assert (assignments.split == "embargo").any()


def test_future_resolving_label_is_purged():
    frame = strict_join(*inputs())
    _, initial = chronological_splits(frame, config())
    val_start = pd.Timestamp(initial["validation_start"])
    index = frame.index[frame.candidate_timestamp < val_start-pd.Timedelta(days=14)][-1]
    frame.loc[index, "resolution_timestamp"] = val_start + pd.Timedelta(days=1)
    assignments, _ = chronological_splits(frame, config())
    assert assignments.loc[index, "split"] == "embargo"


def test_walk_forward_is_expanding_and_leak_free():
    frame = strict_join(*inputs())
    folds = walk_forward_splits(frame, config())
    train_sizes = []
    for _, fold in folds.groupby("fold"):
        train = fold[(fold.role == "train") & fold.supervised_eligible]
        validation = fold[(fold.role == "validation") & fold.supervised_eligible]
        assert train.candidate_timestamp.max() < validation.candidate_timestamp.min()
        assert train.resolution_timestamp.max() < validation.validation_start.iloc[0]
        train_sizes.append(len(train))
    assert train_sizes == sorted(train_sizes)


def test_split_assignments_are_deterministic_under_input_shuffle():
    frame = strict_join(*inputs())
    first, policy1 = chronological_splits(frame, config())
    shuffled = frame.sample(frac=1, random_state=42).reset_index(drop=True)
    second, policy2 = chronological_splits(shuffled, config())
    assert policy1 == policy2
    left = first[["candidate_id", "split"]].sort_values("candidate_id").reset_index(drop=True)
    right = second[["candidate_id", "split"]].sort_values("candidate_id").reset_index(drop=True)
    pd.testing.assert_frame_equal(left, right)


def test_export_manifest_checksum_integrity(monkeypatch, tmp_path):
    # Only this test reaches the Parquet writer, so it alone needs the
    # optional training stack (requirements-training.txt). The rest of the
    # module is pure pandas and must keep running without it.
    pytest.importorskip("pyarrow", reason="needs requirements-training.txt")
    frame = strict_join(*inputs(100))
    splits, policy = chronological_splits(frame, config())
    walk = walk_forward_splits(frame, config())
    frame = frame.merge(splits[["candidate_id", "split", "supervised_eligible", "exclusion_reason"]], on="candidate_id", suffixes=("", "_new"))
    frame["supervised_eligible"] = frame.pop("supervised_eligible_new")
    feature_manifest = {"feature_dataset_id":"fid", "checksum":"fc", "candidate_dataset_id":"cid", "candidate_dataset_checksum":"cc"}
    outcome_manifest = {"outcome_dataset_id":"oid", "checksum":"oc"}
    result = BuildResult(frame, splits, walk, feature_manifest, outcome_manifest, policy)
    monkeypatch.setattr("ml.training_dataset.export.PROJECT_ROOT", tmp_path)
    cfg = SimpleNamespace(version="training_v1", dataset_root=tmp_path/"ml/data/datasets/training_v1", compression="zstd", walk_forward_folds=5)
    output, files, manifest = export_training(result, cfg)
    saved = json.loads((output/"training_manifest.json").read_text())
    assert saved["row_count"] == 100
    assert saved["checksum"] == manifest["checksum"] == _checksum(output, files)
