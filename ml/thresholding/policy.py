"""Validation-only threshold_v2 policy construction and locking."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.dataset as ds

from ml.thresholding.calibration import cross_fit_calibration
from ml.thresholding.config import require_assumptions
from ml.thresholding.metrics import economic_metrics, policy_metrics, safeguards, segment_table
from ml.training.runner import _environment, _sha256, _write_json


def _read_json(path):
    return json.loads(Path(path).read_text("utf-8"))


def _prediction_files(root, trial_id, task):
    files = tuple(sorted((root / "predictions" / trial_id).glob(f"fold_*/{task}_validation.parquet")))
    if len(files) != 5:
        raise ValueError(f"Expected five {task} OOF prediction files for {trial_id}; found {len(files)}")
    return files


def load_oof_predictions(config):
    manifest = _read_json(config.tuning_root / "tuning_manifest.json")
    report = _read_json(config.tuning_root / "tuning_report.json")
    if manifest.get("status") != "complete" or int(manifest.get("completed_jobs", 0)) != 75 or int(manifest.get("test_rows_used", -1)) != 0:
        raise ValueError("A complete, test-excluding tuning_v1 experiment is required")
    selected = report["selected_trials"]
    binary = pd.concat([pd.read_parquet(path) for path in _prediction_files(config.tuning_root, selected["binary"], "binary")], ignore_index=True)
    regression = pd.concat([pd.read_parquet(path) for path in _prediction_files(config.tuning_root, selected["regression"], "regression")], ignore_index=True)
    if set(binary.fold) != set(range(1, 6)) or binary[["candidate_id", "fold"]].duplicated().any():
        raise ValueError("Invalid binary OOF fold coverage")
    if regression[["candidate_id", "fold"]].duplicated().any():
        raise ValueError("Invalid regression OOF fold coverage")
    keep = regression[["candidate_id", "fold", "prediction"]].rename(columns={"prediction": "predicted_regression_r"})
    work = binary.rename(columns={"score": "raw_probability"}).merge(keep, on=["candidate_id", "fold"], how="left", validate="one_to_one")
    if work.predicted_regression_r.isna().any():
        raise ValueError("Binary/regression OOF candidate coverage mismatch")
    dataset = ds.dataset(config.dataset_root / "dataset", format="parquet", partitioning="hive", exclude_invalid_files=True)
    metadata = dataset.to_table(columns=["candidate_id", "split", "strategy_name", "timeframe", "direction"]).to_pandas()
    if metadata.candidate_id.duplicated().any():
        raise ValueError("Duplicate training metadata IDs")
    work = work.merge(metadata, on="candidate_id", how="left", validate="many_to_one")
    if work[["strategy_name", "timeframe", "direction", "split"]].isna().any().any():
        raise ValueError("Missing OOF segment metadata")
    if "test" in set(work.split) or not set(work.split).issubset({"train", "validation"}):
        raise ValueError("Untouched test or excluded split entered threshold selection")
    work["candidate_timestamp"] = pd.to_datetime(work.candidate_timestamp, utc=True)
    return work, manifest, selected


def _thresholds(search):
    count = int(round((float(search["stop"]) - float(search["start"])) / float(search["step"])))
    return tuple(round(float(search["start"]) + index * float(search["step"]), 6) for index in range(count + 1))


def _approved_segments(frame, config):
    approved = []
    rows = []
    for (strategy, timeframe), group in frame.groupby(["strategy_name", "timeframe"], dropna=False):
        metrics = policy_metrics(group, np.ones(len(group), dtype=bool), cost_r=config.trading_cost_r)
        checks, eligible = safeguards(metrics, minimum_coverage=0.0,
                                      minimum_positive_folds=int(config.threshold_search["minimum_positive_folds"]),
                                      minimum_count_per_fold=config.minimum_count_per_fold)
        key = f"{strategy}|{timeframe}"
        rows.append({"segment": key, **{key_: value for key_, value in metrics.items() if key_ != "folds"}, **checks, "approved": eligible})
        if eligible:
            approved.append(key)
    return tuple(sorted(approved)), pd.DataFrame(rows)


def _policy_mask(frame, threshold, use_regression, use_segments, approved):
    mask = frame.calibrated_probability >= float(threshold)
    if use_regression:
        mask &= frame.predicted_regression_r > 0
    if use_segments:
        keys = frame.strategy_name.astype(str) + "|" + frame.timeframe.astype(str)
        mask &= keys.isin(approved)
    return mask


def select_and_lock_policy(config, *, output_dir=None):
    require_assumptions(config)
    root = Path(output_dir or config.output_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    if (root / "test_evaluation_state.json").exists():
        raise ValueError("Untouched test evaluation already started; policy selection is frozen")
    work, tuning_manifest, selected_trials = load_oof_predictions(config)
    import yaml
    resolved_config = {**config.raw, "minimum_accepted_candidates_per_fold": config.minimum_count_per_fold, "trading_cost_r": config.trading_cost_r,
                       "training_dataset_root": str(config.dataset_root), "tuning_root": str(config.tuning_root), "output_root": str(root)}
    (root / "config_resolved.yaml").write_text(yaml.safe_dump(resolved_config, sort_keys=True), "utf-8")
    _write_json(root / "environment.json", _environment())
    calibrated, calibration_report, calibrator = cross_fit_calibration(work, config.calibration["methods"])
    ranked = calibrated.calibrated_probability.rank(method="first", pct=True)
    calibrated["confidence_bucket"] = np.minimum(np.ceil(ranked * 10), 10).astype("int16")
    approved, approved_table = _approved_segments(calibrated, config)
    rows = []
    masks = {}
    for threshold in _thresholds(config.threshold_search):
        for use_regression in config.combined_filters["regression_positive"]:
            for use_segments in config.combined_filters["approved_strategy_timeframe_segments"]:
                policy_id = f"p_{threshold:.3f}_r{int(use_regression)}_s{int(use_segments)}"
                mask = _policy_mask(calibrated, threshold, bool(use_regression), bool(use_segments), approved)
                metrics = policy_metrics(calibrated, mask, cost_r=config.trading_cost_r)
                checks, eligible = safeguards(metrics, minimum_coverage=float(config.threshold_search["minimum_coverage"]),
                                              minimum_positive_folds=int(config.threshold_search["minimum_positive_folds"]),
                                              minimum_count_per_fold=config.minimum_count_per_fold)
                score = metrics["mean_r"] * np.sqrt(metrics["coverage"]) - float(config.threshold_search["stability_penalty"]) * metrics["fold_mean_r_std"]
                rows.append({"policy_id": policy_id, "threshold": threshold, "require_positive_regression_r": bool(use_regression),
                             "require_approved_segment": bool(use_segments), **{key: value for key, value in metrics.items() if key != "folds"},
                             **checks, "eligible": eligible, "stability_score": float(score), "folds": metrics["folds"]})
                masks[policy_id] = mask
    rows.sort(key=lambda row: (-int(row["eligible"]), -row["stability_score"], -row["coverage"], row["policy_id"]))
    eligible = [row for row in rows if row["eligible"]]
    winner = eligible[0] if eligible else None
    bucket_edges = [float(value) for value in calibrated.calibrated_probability.quantile(np.linspace(0, 1, 11)).to_numpy()]
    import joblib
    joblib.dump(calibrator, root / "binary_calibrator.joblib")
    calibrated.to_parquet(root / "calibrated_oof_predictions.parquet", index=False, compression="zstd")
    approved_table.to_parquet(root / "approved_segment_analysis.parquet", index=False, compression="zstd")
    pd.DataFrame([{key: value for key, value in row.items() if key != "folds"} for row in rows]).to_parquet(root / "policy_candidates.parquet", index=False, compression="zstd")
    _write_json(root / "calibration_report.json", calibration_report)
    _write_json(root / "policy_table.json", rows)
    comparisons = {
        "all_strategy_candidates": policy_metrics(calibrated, np.ones(len(calibrated), dtype=bool), cost_r=config.trading_cost_r),
        "threshold_v1": policy_metrics(calibrated, calibrated.raw_probability >= config.threshold_v1_probability, cost_r=config.trading_cost_r),
        "threshold_v2": policy_metrics(calibrated, masks[winner["policy_id"]], cost_r=config.trading_cost_r) if winner else None,
    }
    cost_sensitivity = {}
    for cost in (config.trading_cost_r, *config.cost_sensitivity_r):
        cost_key = f"{cost:.2f}R"
        v2_metrics = policy_metrics(calibrated, masks[winner["policy_id"]], cost_r=cost) if winner else None
        if v2_metrics is not None:
            sensitivity_checks, sensitivity_passed = safeguards(
                v2_metrics,
                minimum_coverage=float(config.threshold_search["minimum_coverage"]),
                minimum_positive_folds=int(config.threshold_search["minimum_positive_folds"]),
                minimum_count_per_fold=config.minimum_count_per_fold,
            )
        else:
            sensitivity_checks, sensitivity_passed = {}, False
        cost_sensitivity[cost_key] = {
            "cost_r": cost,
            "all_strategy_candidates": policy_metrics(calibrated, np.ones(len(calibrated), dtype=bool), cost_r=cost),
            "threshold_v1": policy_metrics(calibrated, calibrated.raw_probability >= config.threshold_v1_probability, cost_r=cost),
            "threshold_v2": v2_metrics,
            "threshold_v2_safeguards": sensitivity_checks,
            "threshold_v2_passed_all_safeguards": sensitivity_passed,
        }
    locked = None
    if winner:
        locked = {"version": "threshold_v2", "status": "locked", "created_at": datetime.now(timezone.utc).isoformat(),
                  "policy_id": winner["policy_id"], "calibration_method": calibration_report["selected_method"],
                  "calibrator_file": "binary_calibrator.joblib", "calibrated_probability_threshold": winner["threshold"],
                  "require_positive_regression_r": winner["require_positive_regression_r"],
                  "require_approved_segment": winner["require_approved_segment"], "approved_strategy_timeframe_segments": list(approved),
                  "confidence_bucket_edges": bucket_edges, "minimum_accepted_candidates_per_fold": config.minimum_count_per_fold,
                  "trading_cost_r": config.trading_cost_r, "cost_sensitivity_r": list(config.cost_sensitivity_r), "validation_metrics": winner,
                  "selected_trials": selected_trials, "training_dataset_id": tuning_manifest["training_dataset_id"],
                  "training_dataset_checksum": tuning_manifest["training_dataset_checksum"],
                  "test_policy": "untouched; evaluate exactly once only after explicit confirmation", "deployment_status": "not_approved"}
        _write_json(root / "locked_policy.json", locked)
    report = {"version": "threshold_v2", "created_at": datetime.now(timezone.utc).isoformat(), "status": "locked" if locked else "rejected",
              "selection_data": "cross-fitted validation OOF predictions only; test excluded", "calibration": calibration_report,
              "approved_segments": list(approved), "winner": winner, "comparisons": comparisons,
              "cost_sensitivity": cost_sensitivity,
              "candidate_policy_count": len(rows), "eligible_policy_count": len(eligible), "deployment_status": "not_approved"}
    _write_json(root / "threshold_v2_report.json", report)
    segment_mask = masks[winner["policy_id"]] if winner else np.zeros(len(calibrated), dtype=bool)
    segment_table(calibrated, segment_mask, config.segment_dimensions, cost_r=config.trading_cost_r).to_parquet(root / "segment_performance.parquet", index=False, compression="zstd")
    lines = ["# threshold_v2 validation report", "", f"- Status: `{report['status']}`", f"- Calibration: `{calibration_report['selected_method']}`",
             f"- Candidate policies: `{len(rows)}`", f"- Eligible policies: `{len(eligible)}`", ""]
    if winner:
        lines += [f"- Locked policy: `{winner['policy_id']}`", f"- Threshold: `{winner['threshold']}`", f"- Coverage: `{winner['coverage']}`",
                  f"- Candidate count: `{winner['candidate_count']}`", f"- Mean R after cost: `{winner['mean_r']}`", f"- Total R after cost: `{winner['total_r']}`",
                  f"- Positive folds: `{winner['positive_folds']} / 5`", ""]
        for cost_key, values in cost_sensitivity.items():
            metrics = values["threshold_v2"]
            lines += [f"## Cost sensitivity {cost_key}", "", f"- Passed all safeguards: `{values['threshold_v2_passed_all_safeguards']}`",
                      f"- Mean R: `{metrics['mean_r']}`", f"- Total R: `{metrics['total_r']}`", f"- Profit factor: `{metrics['profit_factor']}`",
                      f"- Maximum drawdown R: `{metrics['maximum_drawdown_r']}`", f"- Positive folds: `{metrics['positive_folds']} / 5`", ""]
    else:
        lines += ["No policy passed every hard safeguard. The untouched test must remain locked.", ""]
    lines += ["This report is validation-only and is not deployment approval.", ""]
    (root / "threshold_v2_report.md").write_text("\n".join(lines), "utf-8")
    manifest = {"version": "threshold_v2", "status": report["status"], "training_dataset_id": tuning_manifest["training_dataset_id"],
                "training_dataset_checksum": tuning_manifest["training_dataset_checksum"], "tuning_completed_jobs": tuning_manifest["completed_jobs"],
                "oof_rows": len(calibrated), "folds": 5, "test_rows_used": 0, "locked_policy_count": int(locked is not None),
                "minimum_accepted_candidates_per_fold": config.minimum_count_per_fold, "trading_cost_r": config.trading_cost_r,
                "cost_sensitivity_r": list(config.cost_sensitivity_r),
                "deployment_status": "not_approved"}
    _write_json(root / "threshold_v2_manifest.json", manifest)
    files = tuple(sorted(path for path in root.rglob("*") if path.is_file() and path.name != "artifact_checksums.json"))
    _write_json(root / "artifact_checksums.json", {str(path.relative_to(root)).replace("\\", "/"): _sha256(path) for path in files})
    return manifest
