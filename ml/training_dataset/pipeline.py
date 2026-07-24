import json

import pandas as pd
import pyarrow.dataset as ds

from ml.replay.replay_export import _checksum
from ml.training_dataset.builder import BuildResult, chronological_splits, strict_join, walk_forward_splits
from ml.training_dataset.config import TrainingConfigurationError


def _load_manifest(path, root, count_field):
    if not path.is_file(): raise TrainingConfigurationError(f"Manifest missing: {path}")
    manifest = json.loads(path.read_text("utf-8")); files = tuple(sorted(root.rglob("*.parquet")))
    if len(files) != int(manifest["file_count"]) or _checksum(root, files) != manifest["checksum"]:
        raise TrainingConfigurationError(f"Dataset checksum/file count mismatch: {root}")
    if int(manifest[count_field]) != 65441: raise TrainingConfigurationError(f"Unexpected upstream row count: {manifest[count_field]}")
    return manifest


def _read(root):
    return ds.dataset(root, format="parquet", partitioning="hive", exclude_invalid_files=True).to_table().to_pandas()


def build_training_dataset(config, *, limit=None):
    feature_manifest = _load_manifest(config.feature_manifest_path, config.features_root, "feature_count")
    outcome_manifest = _load_manifest(config.outcome_manifest_path, config.outcomes_root, "outcome_count")
    keys = ("candidate_dataset_id", "candidate_dataset_checksum", "source_dataset_id", "source_dataset_checksum")
    if any(feature_manifest[key] != outcome_manifest[key] for key in keys): raise TrainingConfigurationError("Feature/outcome provenance mismatch")
    features = _read(config.features_root); outcomes = _read(config.outcomes_root)
    if limit is not None:
        ids = features.sort_values(["candidate_timestamp", "candidate_id"]).head(limit).candidate_id
        features = features[features.candidate_id.isin(ids)]; outcomes = outcomes[outcomes.candidate_id.isin(ids)]
    dataset = strict_join(features, outcomes)
    splits, policy = chronological_splits(dataset, config)
    walk = walk_forward_splits(dataset, config)
    dataset = dataset.merge(splits[["candidate_id", "split", "supervised_eligible", "exclusion_reason"]], on="candidate_id", validate="one_to_one", suffixes=("", "_assignment"))
    dataset["supervised_eligible"] = dataset["supervised_eligible_assignment"]
    dataset = dataset.drop(columns="supervised_eligible_assignment")
    return BuildResult(dataset, splits, walk, feature_manifest, outcome_manifest, policy)

