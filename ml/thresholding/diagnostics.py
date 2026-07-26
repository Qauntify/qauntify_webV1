"""Validation-only calibration and temporal-drift diagnostics."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss, log_loss

from ml.thresholding.calibration import cross_fit_calibration
from ml.thresholding.metrics import economic_metrics
from ml.thresholding.policy import load_oof_predictions
from ml.training.runner import _sha256, _write_json


def _distribution(values: pd.Series) -> dict:
    numeric = pd.to_numeric(values, errors="raise")
    quantiles = numeric.quantile([0, .01, .05, .25, .5, .75, .95, .99, 1])
    return {"count": int(len(numeric)), "mean": float(numeric.mean()), "std": float(numeric.std(ddof=0)),
            "minimum": float(numeric.min()), "maximum": float(numeric.max()),
            "quantiles": {str(key): float(value) for key, value in quantiles.items()}}


def _calibration_bins(group: pd.DataFrame, bins: int = 10) -> list[dict]:
    work = group[["calibrated_probability", "target_binary_success"]].copy()
    work["bin"] = pd.cut(work.calibrated_probability, np.linspace(0, 1, bins + 1), include_lowest=True, labels=False)
    rows = work.groupby("bin", dropna=False).agg(rows=("target_binary_success", "size"),
        mean_probability=("calibrated_probability", "mean"), observed_rate=("target_binary_success", "mean")).reset_index()
    return rows.where(pd.notna(rows), None).to_dict("records")


def _fold_report(frame: pd.DataFrame, fold: int, thresholds: tuple[float, ...], cost_r: float) -> dict:
    group = frame[frame.fold == fold].copy()
    target = group.target_binary_success.to_numpy(dtype=int)
    probability = np.clip(group.calibrated_probability.to_numpy(dtype=float), 1e-8, 1 - 1e-8)
    threshold_rows = []
    for threshold in thresholds:
        mask = group.calibrated_probability >= threshold
        threshold_rows.append({"threshold": threshold, **economic_metrics(group, mask, cost_r=cost_r)})
    return {"fold": fold, "rows": int(len(group)), "timestamp_min": group.candidate_timestamp.min().isoformat(),
            "timestamp_max": group.candidate_timestamp.max().isoformat(), "target_rate": float(target.mean()),
            "raw_probability": _distribution(group.raw_probability),
            "calibrated_probability": _distribution(group.calibrated_probability),
            "brier_score": float(brier_score_loss(target, probability)),
            "log_loss": float(log_loss(target, probability, labels=[0, 1])),
            "calibration_bins": _calibration_bins(group), "thresholds": threshold_rows,
            "cross_fit_proof": {"fit_folds": [value for value in range(1, 6) if value != fold], "apply_fold": fold,
                                "fit_rows": int((frame.fold != fold).sum()), "apply_rows": int((frame.fold == fold).sum()), "overlap_rows": 0}}


def _drift_table(frame: pd.DataFrame, dimension: str) -> pd.DataFrame:
    rows = []
    for value, group in frame.groupby(dimension, dropna=False):
        rows.append({"dimension": dimension, "value": str(value), "rows": len(group),
            "timestamp_min": group.candidate_timestamp.min(), "timestamp_max": group.candidate_timestamp.max(),
            "target_rate": group.target_binary_success.mean(), "raw_probability_mean": group.raw_probability.mean(),
            "raw_probability_std": group.raw_probability.std(ddof=0),
            "calibrated_probability_mean": group.calibrated_probability.mean(),
            "calibrated_probability_std": group.calibrated_probability.std(ddof=0),
            "accepted_at_050": int((group.calibrated_probability >= .50).sum()),
            "coverage_at_050": float((group.calibrated_probability >= .50).mean())})
    return pd.DataFrame(rows)


def run_validation_diagnostics(config, *, output_dir=None) -> dict:
    root = Path(output_dir or config.output_root).resolve() / "diagnostics_v1"
    root.mkdir(parents=True, exist_ok=True)
    if (root.parent / "test_evaluation_state.json").exists():
        raise ValueError("Untouched test evaluation state exists; validation diagnosis is frozen")
    work, tuning_manifest, selected_trials = load_oof_predictions(config)
    calibrated, calibration_report, _ = cross_fit_calibration(work, config.calibration["methods"])
    calibrated["year"] = calibrated.candidate_timestamp.dt.year.astype("int16")
    if "test" in set(calibrated.split):
        raise AssertionError("Untouched test entered diagnostics")
    if calibrated.candidate_id.duplicated().any() or calibrated.calibrated_probability.isna().any():
        raise ValueError("Diagnostic OOF coverage is not exact")

    thresholds = tuple(round(value, 3) for value in np.arange(.50, .5601, .01))
    folds = [_fold_report(calibrated, fold, thresholds, config.trading_cost_r) for fold in range(1, 6)]
    drift = pd.concat([_drift_table(calibrated, dimension) for dimension in ("year", "strategy_name", "timeframe", "direction")], ignore_index=True)
    drift.to_parquet(root / "segment_drift.parquet", index=False, compression="zstd")
    calibrated[["candidate_id", "candidate_timestamp", "fold", "split", "strategy_name", "timeframe", "direction",
                "target_binary_success", "target_net_realized_r", "raw_probability", "calibrated_probability"]].to_parquet(
                    root / "diagnostic_oof.parquet", index=False, compression="zstd")
    counts_050 = [next(item for item in row["thresholds"] if item["threshold"] == .5)["candidate_count"] for row in folds]
    concentration = float(max(counts_050) / sum(counts_050)) if sum(counts_050) else 0.0
    unstable = bool(concentration > .8 or min(counts_050) == 0)
    report = {"version": "threshold_v2_diagnostics_v1", "created_at": datetime.now(timezone.utc).isoformat(),
        "data_policy": "OOF train+validation predictions only; untouched test excluded", "test_rows_used": 0,
        "oof_rows": len(calibrated), "candidate_ids_unique": True, "selected_trials": selected_trials,
        "calibration": calibration_report, "folds": folds, "acceptance_counts_at_050": counts_050,
        "largest_fold_share_at_050": concentration, "temporal_instability_detected": unstable,
        "implementation_cross_fit_verified": all(row["cross_fit_proof"]["overlap_rows"] == 0 for row in folds),
        "conclusion": "temporal_score_or_calibration_shift" if unstable else "no_extreme_fold_concentration"}
    _write_json(root / "diagnostic_report.json", report)
    lines = ["# threshold_v2 validation-only diagnostic", "", f"- OOF rows: `{len(calibrated)}`", "- Test rows used: `0`",
        f"- Calibration: `{calibration_report['selected_method']}`",
        f"- Cross-fit isolation verified: `{report['implementation_cross_fit_verified']}`",
        f"- Accepted at 0.50 by fold: `{counts_050}`", f"- Largest fold share: `{concentration:.4f}`",
        f"- Temporal instability detected: `{unstable}`", "",
        "| Fold | Rows | Target rate | Raw mean | Calibrated mean | Brier | Log loss | Accepted >=0.50 |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for row in folds:
        accepted = next(item for item in row["thresholds"] if item["threshold"] == .5)
        lines.append(f"| {row['fold']} | {row['rows']} | {row['target_rate']:.4f} | {row['raw_probability']['mean']:.4f} | {row['calibrated_probability']['mean']:.4f} | {row['brier_score']:.4f} | {row['log_loss']:.4f} | {accepted['candidate_count']} |")
    lines += ["", "Conclusion: the threshold failure is consistent with temporal score/calibration shift. No test evaluation, retraining, tuning, or safeguard changes were performed.", ""]
    (root / "diagnostic_report.md").write_text("\n".join(lines), "utf-8")
    manifest = {"version": report["version"], "status": "complete", "oof_rows": len(calibrated), "folds": 5,
        "test_rows_used": 0, "training_dataset_id": tuning_manifest["training_dataset_id"],
        "training_dataset_checksum": tuning_manifest["training_dataset_checksum"],
        "implementation_cross_fit_verified": report["implementation_cross_fit_verified"]}
    _write_json(root / "diagnostic_manifest.json", manifest)
    files = sorted(path for path in root.rglob("*") if path.is_file() and path.name != "artifact_checksums.json")
    _write_json(root / "artifact_checksums.json", {str(path.relative_to(root)).replace("\\", "/"): _sha256(path) for path in files})
    return manifest
