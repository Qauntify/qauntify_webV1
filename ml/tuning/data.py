"""Build nested purged tuning folds without exposing chronological test rows."""
from __future__ import annotations

from dataclasses import replace

import pandas as pd
import pyarrow.dataset as ds

from ml.training.data import TrainingData


def _boundary(frame, fraction):
    ordered = frame.sort_values(["candidate_timestamp", "candidate_id"], kind="mergesort")
    index = min(max(int(len(ordered) * fraction), 1), len(ordered) - 1)
    return pd.Timestamp(ordered.candidate_timestamp.iloc[index])


def build_tuning_folds(data: TrainingData, dataset_root, policy: dict, *, metadata=None):
    """Create five expanding folds strictly from frozen train+validation rows."""
    pool = pd.concat([data.frames["train"], data.frames["validation"]], ignore_index=True)
    if metadata is None:
        assignments = ds.dataset(dataset_root / "split_assignments", format="parquet", partitioning="hive", exclude_invalid_files=True)
        metadata = assignments.to_table(columns=["candidate_id", "resolution_timestamp", "split", "supervised_eligible"]).to_pandas()
    else:
        metadata = metadata.copy()
    metadata = metadata[metadata.split.isin(policy["source_splits"]) & metadata.supervised_eligible]
    if metadata.candidate_id.duplicated().any():
        raise ValueError("Duplicate split metadata entered tuning folds")
    pool = pool.merge(metadata[["candidate_id", "resolution_timestamp", "split"]], on="candidate_id", how="left", validate="one_to_one", suffixes=("", "_frozen"))
    if pool.resolution_timestamp.isna().all() or pool.split_frozen.isna().any():
        raise ValueError("Tuning fold metadata coverage mismatch")
    if set(pool.split_frozen) - set(policy["source_splits"]):
        raise ValueError("Excluded chronological split entered tuning folds")
    timestamp = pd.to_datetime(pool.candidate_timestamp, utc=True)
    resolution = pd.to_datetime(pool.resolution_timestamp, utc=True)
    embargo = pd.Timedelta(days=int(policy["embargo_days"]))
    walk = {}
    validation_ids = set()
    for fold in range(1, int(policy["folds"]) + 1):
        start_fraction = float(policy["initial_train_fraction"]) + (fold - 1) * float(policy["validation_fraction"])
        end_fraction = min(start_fraction + float(policy["validation_fraction"]), 1.0)
        validation_start = _boundary(pool, start_fraction)
        validation_end = _boundary(pool, end_fraction) if end_fraction < 1 else timestamp.max() + pd.Timedelta(microseconds=1)
        train_mask = (timestamp < validation_start - embargo) & (resolution.isna() | (resolution < validation_start))
        validation_mask = (timestamp >= validation_start) & (timestamp < validation_end)
        train = pool[train_mask].drop(columns=["resolution_timestamp", "split_frozen"]).copy()
        validation = pool[validation_mask].drop(columns=["resolution_timestamp", "split_frozen"]).copy()
        if train.empty or validation.empty:
            raise ValueError(f"Tuning fold {fold} is empty")
        if train.candidate_timestamp.max() >= validation.candidate_timestamp.min():
            raise ValueError(f"Tuning fold {fold} chronology violation")
        if validation_ids.intersection(validation.candidate_id):
            raise ValueError("Tuning validation windows overlap")
        validation_ids.update(validation.candidate_id)
        walk[fold] = {"train": train, "validation": validation}
    frozen_test_ids = set(data.frames["test"].candidate_id)
    used_ids = set().union(*(set(frame.candidate_id) for frames in walk.values() for frame in frames.values()))
    if used_ids & frozen_test_ids:
        raise ValueError("Untouched chronological test candidates entered tuning folds")
    return replace(data, walk_forward=walk)
