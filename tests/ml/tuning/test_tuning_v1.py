import json
from pathlib import Path

import numpy as np
import pandas as pd

from ml.tuning.config import load_tuning_config
from ml.tuning.data import build_tuning_folds
from ml.tuning.selection import rank_trials, select_binary_threshold
from ml.training.data import TrainingData


def _folds(values, train_offset=0.02):
    return {str(index): {"validation": {"roc_auc": value, "macro_f1": value, "rmse": value},
                         "train": {"roc_auc": value + train_offset, "macro_f1": value + train_offset, "rmse": value - train_offset}}
            for index, value in enumerate(values, 1)}


def test_tuning_config_is_bounded_and_test_excluding():
    config = load_tuning_config(Path("ml/configs/tuning_v1.yaml"))
    assert config.version == "tuning_v1"
    assert config.base.model_family == "catboost"
    assert config.tasks == ("binary", "multiclass", "regression")
    assert 1 <= len(config.trials) <= 8
    assert config.smoke["trial_limit"] == 1
    assert config.tuning_folds["source_splits"] == ["train", "validation"]
    assert "test" in config.tuning_folds["excluded_splits"]


def test_trial_ranking_uses_fold_mean_stability_and_direction():
    metrics = {
        "stable": {"binary": _folds([0.60] * 5), "multiclass": _folds([0.32] * 5), "regression": _folds([1.10] * 5)},
        "unstable": {"binary": _folds([0.52, 0.70, 0.52, 0.70, 0.52]), "multiclass": _folds([0.20, 0.45, 0.20, 0.45, 0.20]),
                     "regression": _folds([0.9, 1.3, 0.9, 1.3, 0.9])},
    }
    policy = {"primary_metrics": {"binary": "roc_auc", "multiclass": "macro_f1", "regression": "rmse"},
              "metric_directions": {"binary": 1, "multiclass": 1, "regression": -1}, "fold_std_penalty": 0.5,
              "overfit_penalty": 0.25, "temporal_slope_penalty": 0.5}
    ranked = rank_trials(metrics, policy, ("binary", "multiclass", "regression"))
    assert ranked["binary"][0]["trial_id"] == "stable"
    assert ranked["multiclass"][0]["trial_id"] == "stable"
    assert ranked["regression"][0]["trial_id"] == "stable"


def test_binary_threshold_uses_only_oof_rows_and_documents_policy():
    predictions = pd.DataFrame({"fold": np.repeat(np.arange(1, 6), 4),
        "score": np.tile([0.51, 0.61, 0.71, 0.81], 5), "target_binary_success": np.tile([0, 0, 1, 1], 5),
        "target_net_realized_r": np.tile([-1.0, -0.5, 1.0, 1.5], 5)})
    result = select_binary_threshold(predictions, {"values": [0.5, 0.6, 0.7, 0.8], "minimum_coverage": 0.05, "fold_std_penalty": 0.5})
    assert result["selected"]["threshold"] in {0.7, 0.8}
    assert result["selected"]["mean_net_realized_r"] > 0
    assert "test excluded" in result["selection_data_policy"]


def test_nested_tuning_folds_exclude_frozen_test_ids(tmp_path):
    timestamps = pd.date_range("2020-01-01", periods=120, freq="D", tz="UTC")
    frame = pd.DataFrame({"candidate_id": [f"id-{i}" for i in range(120)], "candidate_timestamp": timestamps,
        "split": ["train"] * 70 + ["validation"] * 30 + ["test"] * 20, "numeric": np.arange(120),
        "target_binary_success": [0, 1] * 60, "target_outcome_class": ["sl", "tp"] * 60,
        "target_net_realized_r": [-1.0, 1.0] * 60})
    data = TrainingData({"train": frame.iloc[:70].copy(), "validation": frame.iloc[70:100].copy(), "test": frame.iloc[100:].copy()},
                        ("numeric",), (), {"training_dataset_id": "x", "checksum": "y"}, {})
    metadata = frame[["candidate_id", "split"]].copy()
    metadata["resolution_timestamp"] = frame.candidate_timestamp + pd.Timedelta(hours=1)
    metadata["supervised_eligible"] = True
    policy = {"folds": 5, "initial_train_fraction": 0.5, "validation_fraction": 0.1, "embargo_days": 2,
              "source_splits": ["train", "validation"], "excluded_splits": ["test", "embargo"]}
    result = build_tuning_folds(data, tmp_path, policy, metadata=metadata)
    test_ids = set(data.frames["test"].candidate_id)
    assert len(result.walk_forward) == 5
    assert all(not (set(frame.candidate_id) & test_ids) for fold in result.walk_forward.values() for frame in fold.values())
    assert all(fold["train"].candidate_timestamp.max() < fold["validation"].candidate_timestamp.min() for fold in result.walk_forward.values())


def test_colab_notebook_delegates_to_tuning_cli():
    notebook = json.loads(Path("ml/notebooks/tuning_v1_colab.ipynb").read_text("utf-8"))
    source = "\n".join("".join(cell.get("source", [])) for cell in notebook["cells"])
    assert "drive.mount('/content/drive')" in source
    assert "ml.tuning.cli" in source and "--resume" in source
    assert "ml/configs/tuning_v1.yaml" in source
    assert "CatBoostClassifier(" not in source
    assert "test split is excluded" in source.lower()
