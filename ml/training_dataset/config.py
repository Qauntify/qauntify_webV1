from dataclasses import dataclass
from pathlib import Path

from ml.data.load_dataset import PROJECT_ROOT

DEFAULT_CONFIG_PATH = PROJECT_ROOT / "ml" / "configs" / "training_v1.yaml"
PARTITION_COLUMNS = ("split", "strategy_name", "timeframe", "year")


class TrainingConfigurationError(ValueError): pass


@dataclass(frozen=True)
class TrainingConfig:
    version: str; features_root: Path; feature_manifest_path: Path
    outcomes_root: Path; outcome_manifest_path: Path; dataset_root: Path; reports_root: Path
    train_fraction: float; validation_fraction: float; test_fraction: float; embargo_days: int
    walk_forward_folds: int; walk_initial_fraction: float; walk_validation_fraction: float
    partition_columns: tuple[str, ...]; compression: str


def _repo(value, field):
    path = Path(str(value)); resolved = path.resolve() if path.is_absolute() else (PROJECT_ROOT / path).resolve()
    try: resolved.relative_to(PROJECT_ROOT)
    except ValueError as exc: raise TrainingConfigurationError(f"{field} must remain inside repository") from exc
    return resolved


def load_training_config(path: Path = DEFAULT_CONFIG_PATH):
    import yaml
    path = path.resolve() if path.is_absolute() else (PROJECT_ROOT / path).resolve(); raw = yaml.safe_load(path.read_text("utf-8"))
    if raw.get("version") != "training_v1": raise TrainingConfigurationError("Only training_v1 is supported")
    target = raw.get("targets", {})
    if target.get("multiclass") != "outcome_class" or target.get("regression") != "net_realized_r": raise TrainingConfigurationError("Required targets cannot be changed")
    if target.get("binary") != {"name": "binary_success", "rule": "net_realized_r_strictly_greater_than_zero"}: raise TrainingConfigurationError("Binary success must be net R > 0")
    if target.get("right_censored_policy") != "retain_but_supervised_ineligible": raise TrainingConfigurationError("Censored policy cannot be relaxed")
    split = raw["chronological_split"]; fractions = tuple(float(split[k]) for k in ("train_fraction", "validation_fraction", "test_fraction"))
    if abs(sum(fractions)-1) > 1e-12 or any(x <= 0 for x in fractions): raise TrainingConfigurationError("Split fractions must be positive and sum to one")
    walk = raw["walk_forward"]
    if split.get("purge_label_windows") is not True or walk.get("purge_label_windows") is not True or walk.get("expanding_window") is not True: raise TrainingConfigurationError("Temporal purging and expanding folds are mandatory")
    if int(split["embargo_days"]) != int(walk["embargo_days"]) or int(split["embargo_days"]) < 14: raise TrainingConfigurationError("Embargo must cover the 14-day maximum label horizon")
    partitions = tuple(raw.get("partition_columns", ()))
    if partitions != PARTITION_COLUMNS: raise TrainingConfigurationError("Unexpected partition columns")
    if raw.get("fail_on_any_join_mismatch") is not True: raise TrainingConfigurationError("Strict joins are mandatory")
    compression = str(raw.get("compression", "zstd"));
    if compression not in {"zstd", "snappy"}: raise TrainingConfigurationError("Unsupported compression")
    return TrainingConfig("training_v1", _repo(raw["input"]["features_root"], "features"), _repo(raw["input"]["feature_manifest_path"], "feature manifest"),
        _repo(raw["input"]["outcomes_root"], "outcomes"), _repo(raw["input"]["outcome_manifest_path"], "outcome manifest"),
        _repo(raw["output"]["dataset_root"], "dataset"), _repo(raw["output"]["reports_root"], "reports"),
        *fractions, int(split["embargo_days"]), int(walk["folds"]), float(walk["initial_train_fraction"]), float(walk["validation_fraction"]), partitions, compression)

