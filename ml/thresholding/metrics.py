"""Economic metrics and hard policy safeguards."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd


def economic_metrics(frame: pd.DataFrame, accepted, *, cost_r: float, total_rows=None):
    mask = pd.Series(np.asarray(accepted, dtype=bool), index=frame.index)
    chosen = frame.loc[mask].sort_values(["candidate_timestamp", "candidate_id"], kind="mergesort").copy()
    total = int(total_rows if total_rows is not None else len(frame))
    chosen["net_after_cost_r"] = pd.to_numeric(chosen.target_net_realized_r) - float(cost_r)
    returns = chosen.net_after_cost_r.to_numpy(dtype=float)
    gains = float(returns[returns > 0].sum()) if len(returns) else 0.0
    losses = float(-returns[returns < 0].sum()) if len(returns) else 0.0
    curve = np.cumsum(returns)
    peak = np.maximum.accumulate(np.concatenate([[0.0], curve]))[1:] if len(curve) else np.asarray([])
    drawdown = curve - peak if len(curve) else np.asarray([])
    return {
        "candidate_count": int(len(chosen)),
        "coverage": float(len(chosen) / total) if total else 0.0,
        "win_rate": float((returns > 0).mean()) if len(returns) else 0.0,
        "mean_r": float(returns.mean()) if len(returns) else 0.0,
        "total_r": float(returns.sum()) if len(returns) else 0.0,
        "profit_factor": float(gains / losses) if losses > 0 else None,
        "maximum_drawdown_r": float(drawdown.min()) if len(drawdown) else 0.0,
    }


def policy_metrics(frame: pd.DataFrame, accepted, *, cost_r: float):
    overall = economic_metrics(frame, accepted, cost_r=cost_r)
    mask = pd.Series(np.asarray(accepted, dtype=bool), index=frame.index)
    folds = {}
    for fold_number in range(1, 6):
        fold_mask = frame.fold == fold_number
        folds[str(fold_number)] = economic_metrics(frame.loc[fold_mask], mask.loc[fold_mask], cost_r=cost_r)
    totals = np.asarray([row["total_r"] for row in folds.values()], dtype=float)
    means = np.asarray([row["mean_r"] for row in folds.values()], dtype=float)
    counts = np.asarray([row["candidate_count"] for row in folds.values()], dtype=int)
    overall.update({"folds": folds, "positive_folds": int((totals > 0).sum()), "fold_mean_r_std": float(means.std()),
                    "minimum_fold_candidate_count": int(counts.min()), "fold_consistent": bool((totals > 0).sum() >= 4)})
    return overall


def safeguards(metrics: dict, *, minimum_coverage: float, minimum_positive_folds: int, minimum_count_per_fold: int):
    checks = {
        "positive_mean_net_r": metrics["mean_r"] > 0,
        "positive_total_net_r": metrics["total_r"] > 0,
        "minimum_coverage": metrics["coverage"] >= minimum_coverage,
        "positive_fold_count": metrics["positive_folds"] >= minimum_positive_folds,
        "minimum_candidate_count_per_fold": metrics["minimum_fold_candidate_count"] >= minimum_count_per_fold,
        "positive_after_estimated_costs": metrics["total_r"] > 0 and metrics["mean_r"] > 0,
    }
    return checks, bool(all(checks.values()))


def segment_table(frame, accepted, dimensions, *, cost_r):
    work = frame.copy()
    work["accepted"] = np.asarray(accepted, dtype=bool)
    rows = []
    for dimension in dimensions:
        for value, group in work.groupby(dimension, dropna=False):
            values = economic_metrics(group, group.accepted, cost_r=cost_r)
            rows.append({"dimension": dimension, "value": str(value), **values})
    return pd.DataFrame(rows)
