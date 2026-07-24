"""Strict joins, target creation, and purged chronological split assignment."""
from __future__ import annotations

from dataclasses import dataclass
import pandas as pd

from ml.features.schema import BOOLEAN_FEATURES, CATEGORICAL_FEATURES, NUMERIC_FEATURES

MODEL_FEATURE_COLUMNS = ("strategy_name", "timeframe", "direction") + NUMERIC_FEATURES + BOOLEAN_FEATURES + CATEGORICAL_FEATURES
TARGET_COLUMNS = ("target_outcome_class", "target_net_realized_r", "target_binary_success")
TARGET_METADATA_COLUMNS = ("resolution_timestamp", "holding_seconds", "mfe_r", "mae_r", "right_censored")


@dataclass(frozen=True)
class BuildResult:
    dataset: pd.DataFrame; split_assignments: pd.DataFrame; walk_forward_assignments: pd.DataFrame
    feature_manifest: dict; outcome_manifest: dict; split_policy: dict


def strict_join(features: pd.DataFrame, outcomes: pd.DataFrame):
    for name, frame in (("features", features), ("outcomes", outcomes)):
        if frame.candidate_id.duplicated().any(): raise ValueError(f"Duplicate candidate_id in {name}")
    feature_ids = set(features.candidate_id); outcome_ids = set(outcomes.candidate_id)
    if feature_ids != outcome_ids: raise ValueError(f"Join coverage mismatch: features_only={len(feature_ids-outcome_ids)}, outcomes_only={len(outcome_ids-feature_ids)}")
    outcome_columns = ["candidate_id", "outcome_class", "net_realized_r", *TARGET_METADATA_COLUMNS]
    joined = features.merge(outcomes[outcome_columns], on="candidate_id", how="inner", validate="one_to_one")
    if len(joined) != len(features): raise ValueError("One-to-one join changed row count")
    joined["target_outcome_class"] = joined.outcome_class.astype("string")
    joined["target_net_realized_r"] = joined.net_realized_r.astype("Float64")
    joined["target_binary_success"] = (joined.target_net_realized_r > 0).astype("Int8")
    joined.loc[joined.right_censored, ["target_net_realized_r", "target_binary_success"]] = pd.NA
    joined["supervised_eligible"] = ~joined.right_censored
    keep = ["candidate_id", "candidate_timestamp", "source_candle_timestamp", *MODEL_FEATURE_COLUMNS,
            *TARGET_COLUMNS, *TARGET_METADATA_COLUMNS, "supervised_eligible"]
    result = joined[keep].sort_values(["candidate_timestamp", "candidate_id"], kind="mergesort").reset_index(drop=True)
    if result.candidate_id.nunique() != len(result): raise ValueError("Joined IDs are not unique")
    return result


def _boundary(frame, fraction):
    ordered = frame.sort_values(["candidate_timestamp", "candidate_id"], kind="mergesort")
    index = min(max(int(len(ordered) * fraction), 1), len(ordered)-1)
    return pd.Timestamp(ordered.candidate_timestamp.iloc[index])


def chronological_splits(frame, config):
    val_start = _boundary(frame, config.train_fraction)
    test_start = _boundary(frame, config.train_fraction + config.validation_fraction)
    embargo = pd.Timedelta(days=config.embargo_days)
    train_end = val_start - embargo; validation_end = test_start - embargo
    timestamp = pd.to_datetime(frame.candidate_timestamp, utc=True)
    split = pd.Series("embargo", index=frame.index, dtype="string")
    split[timestamp < train_end] = "train"
    split[(timestamp >= val_start) & (timestamp < validation_end)] = "validation"
    split[timestamp >= test_start] = "test"
    # Purge any earlier label whose observation window reaches the next split.
    resolution = pd.to_datetime(frame.resolution_timestamp, utc=True)
    split[(split == "train") & resolution.notna() & (resolution >= val_start)] = "embargo"
    split[(split == "validation") & resolution.notna() & (resolution >= test_start)] = "embargo"
    eligible = frame.supervised_eligible & split.isin(["train", "validation", "test"])
    reason = pd.Series("eligible", index=frame.index, dtype="string")
    reason[split == "embargo"] = "temporal_embargo_or_purge"; reason[frame.right_censored] = "right_censored"
    assignments = pd.DataFrame({"candidate_id": frame.candidate_id, "candidate_timestamp": timestamp,
        "resolution_timestamp": resolution, "split": split, "supervised_eligible": eligible, "exclusion_reason": reason})
    policy = {"validation_start": val_start.isoformat(), "test_start": test_start.isoformat(),
              "train_candidate_end_exclusive": train_end.isoformat(), "validation_candidate_end_exclusive": validation_end.isoformat(),
              "embargo_days": config.embargo_days, "purge_label_windows": True}
    validate_chronology(assignments, policy)
    return assignments, policy


def validate_chronology(assignments, policy):
    eligible = assignments[assignments.supervised_eligible]
    val_start = pd.Timestamp(policy["validation_start"]); test_start = pd.Timestamp(policy["test_start"])
    train = eligible[eligible.split == "train"]; validation = eligible[eligible.split == "validation"]; test = eligible[eligible.split == "test"]
    if any(part.empty for part in (train, validation, test)): raise ValueError("A chronological split is empty")
    if not (train.candidate_timestamp.max() < validation.candidate_timestamp.min() < test.candidate_timestamp.min()): raise ValueError("Split chronology violated")
    if train.resolution_timestamp.notna().any() and train.resolution_timestamp.dropna().max() >= val_start: raise ValueError("Train label window leaks into validation")
    if validation.resolution_timestamp.notna().any() and validation.resolution_timestamp.dropna().max() >= test_start: raise ValueError("Validation label window leaks into test")


def walk_forward_splits(frame, config):
    timestamp = pd.to_datetime(frame.candidate_timestamp, utc=True); resolution = pd.to_datetime(frame.resolution_timestamp, utc=True)
    rows = []
    for fold in range(config.walk_forward_folds):
        start_fraction = config.walk_initial_fraction + fold * config.walk_validation_fraction
        end_fraction = min(start_fraction + config.walk_validation_fraction, 1.0)
        validation_start = _boundary(frame, start_fraction)
        validation_end = _boundary(frame, end_fraction) if end_fraction < 1 else timestamp.max() + pd.Timedelta(microseconds=1)
        train_end = validation_start - pd.Timedelta(days=config.embargo_days)
        role = pd.Series("future", index=frame.index, dtype="string")
        role[timestamp < train_end] = "train"
        role[(timestamp >= train_end) & (timestamp < validation_start)] = "embargo"
        role[(timestamp >= validation_start) & (timestamp < validation_end)] = "validation"
        role[(role == "train") & resolution.notna() & (resolution >= validation_start)] = "embargo"
        eligible = frame.supervised_eligible & role.isin(["train", "validation"])
        fold_frame = pd.DataFrame({"candidate_id": frame.candidate_id, "fold": fold + 1, "role": role,
            "candidate_timestamp": timestamp, "resolution_timestamp": resolution, "supervised_eligible": eligible,
            "validation_start": validation_start, "validation_end": validation_end})
        train = fold_frame[(fold_frame.role == "train") & fold_frame.supervised_eligible]
        validation = fold_frame[(fold_frame.role == "validation") & fold_frame.supervised_eligible]
        if train.empty or validation.empty or train.resolution_timestamp.dropna().max() >= validation_start: raise ValueError(f"Walk-forward leakage in fold {fold+1}")
        rows.append(fold_frame)
    return pd.concat(rows, ignore_index=True)
