"""Exactly-once untouched-test evaluation using frozen fold models; no fitting."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from ml.thresholding.calibration import apply_calibrator
from ml.thresholding.config import require_assumptions
from ml.thresholding.metrics import economic_metrics, segment_table
from ml.training.data import load_verified_training_data
from ml.training.runner import _sha256, _write_json


def _read(path):
    return json.loads(Path(path).read_text("utf-8"))


def _load_models(tuning_root, trial_id, task):
    from catboost import CatBoostClassifier, CatBoostRegressor

    models = []
    for fold in range(1, 6):
        path = tuning_root / "models" / trial_id / f"fold_{fold:02d}" / f"{task}.cbm"
        if not path.is_file():
            raise FileNotFoundError(f"Selected frozen model missing: {path}")
        model = CatBoostRegressor() if task == "regression" else CatBoostClassifier()
        model.load_model(str(path))
        models.append(model)
    return models


def _ensemble_scores(models, frame, features, task):
    X = frame[list(features)]
    if task == "binary":
        values = []
        for model in models:
            classes = list(model.classes_)
            values.append(np.asarray(model.predict_proba(X))[:, classes.index(1)])
        return np.mean(values, axis=0)
    return np.mean([np.asarray(model.predict(X), dtype=float).reshape(-1) for model in models], axis=0)


def _threshold_v2_mask(frame, policy):
    mask = frame.calibrated_probability >= float(policy["calibrated_probability_threshold"])
    if policy["require_positive_regression_r"]:
        mask &= frame.predicted_regression_r > 0
    if policy["require_approved_segment"]:
        keys = frame.strategy_name.astype(str) + "|" + frame.timeframe.astype(str)
        mask &= keys.isin(policy["approved_strategy_timeframe_segments"])
    return mask


def evaluate_untouched_test_once(config, *, output_dir=None, confirmed=False):
    require_assumptions(config)
    if not confirmed:
        raise ValueError("Explicit --confirm-untouched-test is required")
    root = Path(output_dir or config.output_root).resolve()
    policy_path = root / "locked_policy.json"
    if not policy_path.is_file():
        raise ValueError("No locked threshold_v2 policy exists; test evaluation is forbidden")
    state_path = root / "test_evaluation_state.json"
    if state_path.exists():
        raise FileExistsError("Untouched test evaluation has already started and cannot be repeated")
    policy = _read(policy_path)
    if policy["minimum_accepted_candidates_per_fold"] != config.minimum_count_per_fold or float(policy["trading_cost_r"]) != config.trading_cost_r:
        raise ValueError("Configured assumptions differ from the locked policy")
    _write_json(state_path, {"status": "started", "started_at": datetime.now(timezone.utc).isoformat(),
                             "policy_id": policy["policy_id"], "exactly_once_guard": True})
    data = load_verified_training_data(config.base, smoke=False)
    if data.manifest["training_dataset_id"] != policy["training_dataset_id"] or data.manifest["checksum"] != policy["training_dataset_checksum"]:
        raise ValueError("Frozen dataset does not match locked policy")
    test = data.frames["test"].copy()
    if set(test.split) != {"test"}:
        raise ValueError("Untouched test frame identity failed")
    binary_models = _load_models(config.tuning_root, policy["selected_trials"]["binary"], "binary")
    regression_models = _load_models(config.tuning_root, policy["selected_trials"]["regression"], "regression")
    test["raw_probability"] = _ensemble_scores(binary_models, test, data.feature_columns, "binary")
    test["predicted_regression_r"] = _ensemble_scores(regression_models, test, data.feature_columns, "regression")
    import joblib
    calibrator = joblib.load(root / policy["calibrator_file"])
    test["calibrated_probability"] = apply_calibrator(calibrator, policy["calibration_method"], test.raw_probability)
    test["confidence_bucket"] = np.minimum(np.ceil(test.calibrated_probability.rank(method="first", pct=True) * 10), 10).astype("int16")
    all_mask = np.ones(len(test), dtype=bool)
    v1_mask = test.raw_probability >= config.threshold_v1_probability
    v2_mask = _threshold_v2_mask(test, policy)
    comparisons = {
        "all_strategy_candidates": economic_metrics(test, all_mask, cost_r=config.trading_cost_r),
        "threshold_v1": economic_metrics(test, v1_mask, cost_r=config.trading_cost_r),
        "threshold_v2": economic_metrics(test, v2_mask, cost_r=config.trading_cost_r),
    }
    test_output = test[["candidate_id", "candidate_timestamp", "strategy_name", "timeframe", "direction", "target_binary_success",
                        "target_net_realized_r", "raw_probability", "calibrated_probability", "predicted_regression_r", "confidence_bucket"]].copy()
    test_output["accepted_threshold_v1"] = v1_mask
    test_output["accepted_threshold_v2"] = v2_mask
    test_output.to_parquet(root / "untouched_test_predictions.parquet", index=False, compression="zstd")
    segment_table(test, v2_mask, config.segment_dimensions, cost_r=config.trading_cost_r).to_parquet(root / "untouched_test_segments.parquet", index=False, compression="zstd")
    report = {"version": "threshold_v2_test_v1", "evaluated_at": datetime.now(timezone.utc).isoformat(), "policy_id": policy["policy_id"],
              "rows": len(test), "comparisons": comparisons, "selection_influence": "none; policy was locked before this evaluation",
              "test_evaluation_count": 1, "deployment_status": "not_approved"}
    _write_json(root / "untouched_test_report.json", report)
    lines = ["# threshold_v2 untouched-test report", "", "The locked policy was evaluated exactly once. Test results were not used for selection.", ""]
    for name, metrics in comparisons.items():
        lines += [f"## {name}", "", f"- Coverage: `{metrics['coverage']}`", f"- Candidate count: `{metrics['candidate_count']}`",
                  f"- Win rate: `{metrics['win_rate']}`", f"- Mean R: `{metrics['mean_r']}`", f"- Total R: `{metrics['total_r']}`",
                  f"- Profit factor: `{metrics['profit_factor']}`", f"- Maximum drawdown R: `{metrics['maximum_drawdown_r']}`", ""]
    lines += ["This report is evaluation evidence, not deployment approval.", ""]
    (root / "untouched_test_report.md").write_text("\n".join(lines), "utf-8")
    _write_json(state_path, {"status": "complete", "started_at": _read(state_path)["started_at"], "completed_at": datetime.now(timezone.utc).isoformat(),
                             "policy_id": policy["policy_id"], "test_evaluation_count": 1, "exactly_once_guard": True})
    files = tuple(sorted(path for path in root.rglob("*") if path.is_file() and path.name != "artifact_checksums.json"))
    _write_json(root / "artifact_checksums.json", {str(path.relative_to(root)).replace("\\", "/"): _sha256(path) for path in files})
    return report

