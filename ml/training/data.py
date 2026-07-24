"""Verified loading of frozen main and walk-forward training_v1 splits."""
from __future__ import annotations

import json
from dataclasses import dataclass, field

import pandas as pd
import pyarrow.dataset as ds

from ml.replay.replay_export import _checksum


TARGET_BY_TASK = {"binary":"target_binary_success", "multiclass":"target_outcome_class", "regression":"target_net_realized_r"}
GROUP_COLUMNS = ("strategy_name", "timeframe", "direction")


@dataclass(frozen=True)
class TrainingData:
    frames: dict[str, pd.DataFrame]
    feature_columns: tuple[str, ...]
    categorical_columns: tuple[str, ...]
    manifest: dict
    walk_forward: dict[int, dict[str, pd.DataFrame]] = field(default_factory=dict)


def _ordered(frame):
    return frame.sort_values(["candidate_timestamp","candidate_id"], kind="mergesort").reset_index(drop=True)


def _prepare(frame, categorical):
    frame = _ordered(frame.copy())
    frame["year"] = pd.to_datetime(frame.candidate_timestamp, utc=True).dt.year.astype("int16")
    for name in categorical:
        frame[name] = frame[name].astype("string").fillna("__MISSING__")
    return frame


def load_verified_training_data(config, *, smoke=False):
    if not config.manifest_path.is_file(): raise FileNotFoundError(f"Training manifest missing: {config.manifest_path}")
    manifest = json.loads(config.manifest_path.read_text("utf-8"))
    if manifest.get("training_policy_version") != "training_v1" or int(manifest.get("walk_forward_folds",0)) != 5: raise ValueError("Frozen training_v1 with five folds is required")
    files = tuple(sorted(config.dataset_root.rglob("*.parquet")))
    if len(files) != int(manifest["file_count"]) or _checksum(config.dataset_root, files) != manifest["checksum"]: raise ValueError("training_v1 checksum or file count mismatch")
    dataset = ds.dataset(config.dataset_root / "dataset", format="parquet", partitioning="hive", exclude_invalid_files=True)
    feature_columns = tuple(manifest["model_feature_columns"])
    required = {"candidate_id","candidate_timestamp","split","supervised_eligible",*feature_columns,*manifest["target_columns"]}
    if missing := sorted(required-set(dataset.schema.names)): raise ValueError(f"Training columns missing: {missing}")
    future = set(manifest["future_derived_metadata_columns"]); targets = set(manifest["target_columns"])
    if overlap := sorted(set(feature_columns)&(future|targets)): raise ValueError(f"Future-derived columns entered model inputs: {overlap}")
    columns = ["candidate_id","candidate_timestamp","split","supervised_eligible",*feature_columns,*manifest["target_columns"]]
    all_rows = dataset.to_table(columns=columns).to_pandas()
    if all_rows.candidate_id.duplicated().any() or len(all_rows) != int(manifest["row_count"]): raise ValueError("Training dataset ID coverage mismatch")
    categorical = tuple(name for name in feature_columns if not pd.api.types.is_numeric_dtype(all_rows[name]))
    frames = {}
    for split in ("train","validation","test"):
        frame=all_rows[(all_rows.split==split)&all_rows.supervised_eligible]
        if smoke: frame=_ordered(frame).head(config.smoke[f"{split}_rows"])
        if frame.empty: raise ValueError(f"{split} split is empty")
        frames[split]=_prepare(frame,categorical)

    assignments_ds=ds.dataset(config.dataset_root/"walk_forward",format="parquet",partitioning="hive",exclude_invalid_files=True)
    assignments=assignments_ds.to_table(columns=["candidate_id","fold","role","resolution_timestamp","supervised_eligible","validation_start","validation_end"]).to_pandas()
    if len(assignments) != int(manifest["row_count"])*5: raise ValueError("Walk-forward assignment coverage mismatch")
    walk={}
    model_rows=all_rows.drop(columns=["split","supervised_eligible"])
    for fold_number in range(1,6):
        fold_assignments=assignments[(assignments.fold==fold_number)&assignments.supervised_eligible]
        fold_frames={}
        for role in ("train","validation"):
            selected=fold_assignments[fold_assignments.role==role]
            frame=selected[["candidate_id"]].merge(model_rows,on="candidate_id",how="left",validate="one_to_one")
            if frame.isna().all(axis=1).any(): raise ValueError(f"Missing rows in walk-forward fold {fold_number}")
            if smoke: frame=_ordered(frame).head(config.smoke[f"walk_{role}_rows"])
            if frame.empty: raise ValueError(f"Walk-forward fold {fold_number} {role} is empty")
            fold_frames[role]=_prepare(frame,categorical)
        train_resolution=pd.to_datetime(fold_assignments[fold_assignments.role=="train"].resolution_timestamp,utc=True)
        validation_start=pd.to_datetime(fold_assignments.validation_start,utc=True).iloc[0]
        if train_resolution.max() >= validation_start or fold_frames["train"].candidate_timestamp.max() >= fold_frames["validation"].candidate_timestamp.min(): raise ValueError(f"Walk-forward leakage in fold {fold_number}")
        walk[fold_number]=fold_frames
    return TrainingData(frames,feature_columns,categorical,manifest,walk)
