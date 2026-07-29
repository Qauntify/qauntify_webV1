"""Build the leakage-protected training_v3 dataset without fitting models."""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pandas as pd
import pyarrow.dataset as ds
import yaml


VERSION = "training_v3"
LABEL_TARGETS = ("long_net_profitable", "short_net_profitable")
REGRESSION_METADATA = ("long_net_r_base", "short_net_r_base")
LABEL_METADATA = (
    "entry_timestamp", "long_exit_timestamp", "short_exit_timestamp",
    "long_result", "short_result", "right_censored", "invalid_reason",
    "supervised_eligible",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _load_dataset(root: Path, columns: list[str] | None = None) -> pd.DataFrame:
    return ds.dataset(root / "dataset", format="parquet", partitioning="hive").to_table(columns=columns).to_pandas()


def load_model_partition(
    root: Path,
    split: str,
    *,
    allow_untouched_test: bool = False,
    approval_artifact: Path | None = None,
    frozen_policy_manifest: Path | None = None,
) -> pd.DataFrame:
    """Load a supervised split, keeping test inaccessible by default."""
    if split == "untouched_test":
        if not allow_untouched_test:
            raise PermissionError("Untouched test is locked")
        if not approval_artifact or not approval_artifact.is_file():
            raise PermissionError("Untouched-test approval artifact is required")
        if not frozen_policy_manifest or not frozen_policy_manifest.is_file():
            raise PermissionError("Frozen policy manifest is required")
    dataset = ds.dataset(root / "dataset", format="parquet", partitioning="hive")
    return dataset.to_table(filter=ds.field("split") == split).to_pandas()


def strict_join(features: pd.DataFrame, labels: pd.DataFrame, feature_columns: list[str]) -> pd.DataFrame:
    for name, frame in (("features", features), ("labels", labels)):
        if frame["candidate_id"].duplicated().any():
            raise ValueError(f"Duplicate candidate_id in {name}")
    feature_ids, label_ids = set(features.candidate_id), set(labels.candidate_id)
    if feature_ids != label_ids:
        raise ValueError(
            f"Candidate coverage mismatch: features_only={len(feature_ids-label_ids)}, "
            f"labels_only={len(label_ids-feature_ids)}"
        )
    joined = features.merge(labels, on=["candidate_id", "decision_timestamp"], how="inner", validate="one_to_one")
    if len(joined) != len(features):
        raise ValueError("Strict join changed row count")
    forbidden = set(LABEL_TARGETS + REGRESSION_METADATA + LABEL_METADATA)
    overlap = forbidden.intersection(feature_columns)
    if overlap:
        raise ValueError(f"Future-derived columns in feature contract: {sorted(overlap)}")
    joined["training_eligible"] = joined["feature_eligible"] & joined["supervised_eligible"]
    for target in LABEL_TARGETS:
        if joined.loc[joined.training_eligible, target].isna().any():
            raise ValueError(f"Eligible rows have null target: {target}")
    return joined.sort_values(["decision_timestamp", "candidate_id"], kind="mergesort").reset_index(drop=True)


def _timestamp(value: str) -> pd.Timestamp:
    return pd.Timestamp(value)


def _max_exit(frame: pd.DataFrame) -> pd.Series:
    return pd.concat(
        [pd.to_datetime(frame.long_exit_timestamp), pd.to_datetime(frame.short_exit_timestamp)], axis=1
    ).max(axis=1)


def assign_primary_splits(frame: pd.DataFrame, split_cfg: dict) -> pd.DataFrame:
    definition = split_cfg["chronological_split"]
    ts = pd.to_datetime(frame.decision_timestamp)
    exit_ts = _max_exit(frame)
    embargo = pd.Timedelta(minutes=int(split_cfg["protection"]["embargo_minutes"]))
    val_start = _timestamp(definition["validation"]["start_inclusive"])
    test_start = _timestamp(definition["untouched_test"]["start_inclusive"])
    end = _timestamp(definition["untouched_test"]["end_exclusive"])
    split = pd.Series("ineligible", index=frame.index, dtype="string")
    split[frame.training_eligible & (ts < val_start)] = "train"
    split[frame.training_eligible & (ts >= val_start + embargo) & (ts < test_start)] = "validation"
    split[frame.training_eligible & (ts >= test_start + embargo) & (ts < end)] = "untouched_test"
    split[frame.training_eligible & (ts >= val_start) & (ts < val_start + embargo)] = "embargo"
    split[frame.training_eligible & (ts >= test_start) & (ts < test_start + embargo)] = "embargo"
    train_leak = (split == "train") & exit_ts.notna() & (exit_ts >= val_start)
    validation_leak = (split == "validation") & exit_ts.notna() & (exit_ts >= test_start)
    split[train_leak | validation_leak] = "purged"
    result = pd.DataFrame({
        "candidate_id": frame.candidate_id,
        "decision_timestamp": ts,
        "maximum_outcome_exit_timestamp": exit_ts,
        "split": split,
        "training_eligible": frame.training_eligible,
        "test_locked": split.eq("untouched_test"),
    })
    validate_primary_splits(result, val_start, test_start)
    return result


def validate_primary_splits(assignments: pd.DataFrame, val_start: pd.Timestamp, test_start: pd.Timestamp) -> None:
    train = assignments[assignments.split == "train"]
    validation = assignments[assignments.split == "validation"]
    test = assignments[assignments.split == "untouched_test"]
    if any(part.empty for part in (train, validation, test)):
        raise ValueError("A protected chronological split is empty")
    if train.decision_timestamp.max() >= val_start or validation.decision_timestamp.max() >= test_start:
        raise ValueError("Primary split chronology failed")
    if train.maximum_outcome_exit_timestamp.dropna().max() >= val_start:
        raise ValueError("Training outcomes cross validation boundary")
    if validation.maximum_outcome_exit_timestamp.dropna().max() >= test_start:
        raise ValueError("Validation outcomes cross test boundary")


def assign_walk_forward(frame: pd.DataFrame, split_cfg: dict) -> pd.DataFrame:
    ts = pd.to_datetime(frame.decision_timestamp)
    exit_ts = _max_exit(frame)
    embargo = pd.Timedelta(minutes=int(split_cfg["protection"]["embargo_minutes"]))
    outputs = []
    for definition in split_cfg["walk_forward"]["definitions"]:
        train_start = _timestamp(definition["train_start_inclusive"])
        validation_start = _timestamp(definition["validation_start_inclusive"])
        validation_end = _timestamp(definition["validation_end_exclusive"])
        role = pd.Series("outside", index=frame.index, dtype="string")
        eligible = frame.training_eligible
        role[eligible & (ts >= train_start) & (ts < validation_start)] = "train"
        role[eligible & (ts >= validation_start) & (ts < validation_start + embargo)] = "embargo"
        role[eligible & (ts >= validation_start + embargo) & (ts < validation_end)] = "validation"
        crossing = (role == "train") & exit_ts.notna() & (exit_ts >= validation_start)
        role[crossing] = "purged"
        fold = pd.DataFrame({
            "candidate_id": frame.candidate_id,
            "fold": int(definition["fold"]),
            "role": role,
            "decision_timestamp": ts,
            "maximum_outcome_exit_timestamp": exit_ts,
            "training_eligible": eligible,
        })
        train = fold[fold.role == "train"]
        validation = fold[fold.role == "validation"]
        if train.empty or validation.empty or train.maximum_outcome_exit_timestamp.dropna().max() >= validation_start:
            raise ValueError(f"Walk-forward fold {definition['fold']} is empty or leaks")
        outputs.append(fold)
    return pd.concat(outputs, ignore_index=True)


def build(config_path: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict, dict, dict]:
    config = yaml.safe_load(config_path.read_text("utf-8"))
    if config.get("version") != VERSION:
        raise ValueError("Only training_v3 is supported")
    root = config_path.parents[2]
    features_root = root / config["inputs"]["features_root"]
    labels_root = root / config["inputs"]["labels_root"]
    split_path = root / config["inputs"]["split_config"]
    feature_manifest = json.loads((features_root / "feature_manifest.json").read_text("utf-8"))
    label_manifest = json.loads((labels_root / "label_manifest.json").read_text("utf-8"))
    split_cfg = yaml.safe_load(split_path.read_text("utf-8"))
    feature_columns = feature_manifest["feature_columns"]
    features = _load_dataset(features_root, ["candidate_id", "decision_timestamp", "feature_eligible", *feature_columns])
    labels = _load_dataset(labels_root, ["candidate_id", "decision_timestamp", *LABEL_TARGETS, *REGRESSION_METADATA, *LABEL_METADATA])
    joined = strict_join(features, labels, feature_columns)
    primary = assign_primary_splits(joined, split_cfg)
    walk = assign_walk_forward(joined, split_cfg)
    joined = joined.merge(primary[["candidate_id", "split"]], on="candidate_id", validate="one_to_one")
    return joined, primary, walk, config, feature_manifest, label_manifest


def _write_partitioned(frame: pd.DataFrame, root: Path, partitions: list[str]) -> list[Path]:
    root.mkdir(parents=True, exist_ok=True)
    group_key = partitions[0] if len(partitions) == 1 else partitions
    for keys, group in frame.groupby(group_key, sort=True, observed=True):
        keys = (keys,) if len(partitions) == 1 else keys
        directory = root
        for name, value in zip(partitions, keys):
            directory /= f"{name}={value}"
        directory.mkdir(parents=True, exist_ok=True)
        group.drop(columns=partitions).to_parquet(directory / "part-000.parquet", index=False, compression="zstd")
    return sorted(root.rglob("*.parquet"))


def export(config_path: Path, output_root: Path, overwrite: bool = False) -> dict:
    joined, primary, walk, config, feature_manifest, label_manifest = build(config_path)
    if output_root.exists():
        if not overwrite:
            raise FileExistsError(output_root)
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True)
    joined["decision_year"] = pd.to_datetime(joined.decision_timestamp).dt.year.astype("int16")
    files = _write_partitioned(joined, output_root / "dataset", ["split", "decision_year"])
    files += _write_partitioned(primary, output_root / "split_assignments", ["split"])
    files += _write_partitioned(walk, output_root / "walk_forward_assignments", ["fold", "role"])
    checksums = {str(path.relative_to(output_root)): _sha256(path) for path in sorted(files)}
    split_counts = {str(k): int(v) for k, v in primary.split.value_counts().sort_index().items()}
    fold_counts = {
        str(fold): {str(k): int(v) for k, v in group.role.value_counts().sort_index().items()}
        for fold, group in walk.groupby("fold", sort=True)
    }
    manifest = {
        "version": VERSION,
        "approval_status": "pending_review",
        "rows": len(joined),
        "unique_candidate_ids": int(joined.candidate_id.nunique()),
        "training_eligible_rows": int(joined.training_eligible.sum()),
        "feature_version": feature_manifest["version"],
        "feature_dataset_checksum": feature_manifest["dataset_checksum"],
        "label_version": label_manifest["label_version"],
        "label_dataset_checksum": label_manifest["dataset_checksum"],
        "training_config_checksum": _sha256(config_path),
        "feature_manifest_checksum": _sha256(config_path.parents[2] / config["inputs"]["features_root"] / "feature_manifest.json"),
        "label_manifest_checksum": _sha256(config_path.parents[2] / config["inputs"]["labels_root"] / "label_manifest.json"),
        "split_config_checksum": _sha256(config_path.parents[2] / config["inputs"]["split_config"]),
        "model_feature_columns": feature_manifest["feature_columns"],
        "binary_targets": list(LABEL_TARGETS),
        "optional_regression_metadata": list(REGRESSION_METADATA),
        "binary_success_rule": "directional net realised R at base cost is strictly greater than zero",
        "untouched_test_locked": True,
        "split_counts": split_counts,
        "walk_forward_counts": fold_counts,
        "file_checksums": checksums,
    }
    manifest["dataset_checksum"] = hashlib.sha256(json.dumps(checksums, sort_keys=True).encode()).hexdigest().upper()
    (output_root / "training_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", "utf-8")
    return manifest
