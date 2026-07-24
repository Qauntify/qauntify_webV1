"""Deterministic validation-only trial and threshold selection."""
from __future__ import annotations

import math
from collections import defaultdict

import numpy as np
import pandas as pd


def rank_trials(metrics: dict, selection: dict, tasks: tuple[str, ...]):
    """Rank trials using walk-forward validation only; no test metric is accepted."""
    ranked = {}
    for task in tasks:
        primary = selection["primary_metrics"][task]
        direction = int(selection["metric_directions"][task])
        rows = []
        for trial_id, trial_values in sorted(metrics.items()):
            folds = trial_values[task]
            validation = np.asarray([folds[str(fold)]["validation"][primary] for fold in range(1, 6)], dtype=float)
            train = np.asarray([folds[str(fold)]["train"][primary] for fold in range(1, 6)], dtype=float)
            oriented_validation = direction * validation
            overfit = np.maximum(direction * (train - validation), 0.0)
            temporal_slope = float(np.polyfit(np.arange(1, 6), oriented_validation, 1)[0])
            score = float(
                oriented_validation.mean()
                - float(selection["fold_std_penalty"]) * oriented_validation.std()
                - float(selection["overfit_penalty"]) * overfit.mean()
                - float(selection["temporal_slope_penalty"]) * abs(temporal_slope)
            )
            rows.append({
                "trial_id": trial_id,
                "primary_metric": primary,
                "validation_mean": float(validation.mean()),
                "validation_std": float(validation.std()),
                "train_mean": float(train.mean()),
                "mean_overfit_gap_oriented": float(overfit.mean()),
                "temporal_slope_oriented": temporal_slope,
                "selection_score": score,
                "fold_values": validation.tolist(),
            })
        rows.sort(key=lambda row: (-row["selection_score"], row["trial_id"]))
        ranked[task] = rows
    return ranked


def select_binary_threshold(predictions: pd.DataFrame, policy: dict):
    required = {"fold", "score", "target_binary_success", "target_net_realized_r"}
    if missing := sorted(required - set(predictions.columns)):
        raise ValueError(f"Threshold predictions missing columns: {missing}")
    if predictions.empty:
        raise ValueError("Threshold predictions are empty")
    rows = []
    for threshold in (float(value) for value in policy["values"]):
        selected = predictions[predictions.score >= threshold]
        coverage = len(selected) / len(predictions)
        if selected.empty:
            precision = mean_r = total_r = 0.0
        else:
            precision = float(selected.target_binary_success.mean())
            mean_r = float(selected.target_net_realized_r.mean())
            total_r = float(selected.target_net_realized_r.sum())
        fold_means = []
        for _, fold in predictions.groupby("fold"):
            fold_selected = fold[fold.score >= threshold]
            fold_means.append(float(fold_selected.target_net_realized_r.mean()) if not fold_selected.empty else 0.0)
        utility = mean_r * math.sqrt(coverage) - float(policy["fold_std_penalty"]) * float(np.std(fold_means))
        rows.append({"threshold": threshold, "coverage": coverage, "precision": precision, "mean_net_realized_r": mean_r,
                     "total_net_realized_r": total_r, "fold_mean_r_std": float(np.std(fold_means)), "utility": float(utility),
                     "eligible": bool(coverage >= float(policy["minimum_coverage"]))})
    eligible = [row for row in rows if row["eligible"]]
    if not eligible:
        raise ValueError("No threshold satisfies minimum coverage")
    selected = sorted(eligible, key=lambda row: (-row["utility"], -row["mean_net_realized_r"], row["threshold"]))[0]
    return {"selected": selected, "candidates": rows,
            "selection_data_policy": "five walk-forward validation folds only; untouched test excluded"}
