"""Strict configuration for the versioned tuning_v1 policy."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ml.data.load_dataset import PROJECT_ROOT
from ml.training.config import TASKS, ExperimentConfig, load_experiment_config


class TuningConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class TuningConfig:
    version: str
    base: ExperimentConfig
    dataset_root: Path
    artifacts_root: Path
    random_seed: int
    tasks: tuple[str, ...]
    trials: tuple[dict, ...]
    selection: dict
    tuning_folds: dict
    binary_thresholds: dict
    smoke: dict
    raw: dict


def _path(value, *, base=PROJECT_ROOT):
    path = Path(str(value))
    return path.resolve() if path.is_absolute() else (base / path).resolve()


def load_tuning_config(path: Path, *, dataset_root: Path | None = None, artifacts_root: Path | None = None):
    import yaml

    config_path = _path(path)
    raw = yaml.safe_load(config_path.read_text("utf-8"))
    if raw.get("version") != "tuning_v1":
        raise TuningConfigurationError("version must be tuning_v1")
    tasks = tuple(raw.get("tasks", ()))
    if not tasks or len(tasks) != len(set(tasks)) or not set(tasks).issubset(TASKS):
        raise TuningConfigurationError("Invalid tuning task list")
    base_path = _path(raw.get("base_config"))
    ds_root = _path(dataset_root) if dataset_root else _path(raw["training_dataset_root"])
    base = load_experiment_config(base_path, dataset_root=ds_root)
    if base.model_family != "catboost":
        raise TuningConfigurationError("tuning_v1 requires a CatBoost base config")
    trials = tuple(dict(item) for item in raw.get("trials", ()))
    if not trials or len({item.get("name") for item in trials}) != len(trials):
        raise TuningConfigurationError("Trials require unique names")
    required = {"name", "iterations", "depth", "learning_rate", "l2_leaf_reg"}
    for trial in trials:
        if missing := sorted(required - set(trial)):
            raise TuningConfigurationError(f"Trial is missing fields: {missing}")
        if int(trial["iterations"]) <= 0 or int(trial["depth"]) <= 0 or float(trial["learning_rate"]) <= 0:
            raise TuningConfigurationError("Trial numeric values must be positive")
    selection = dict(raw.get("selection", {}))
    directions = selection.get("metric_directions", {})
    if set(selection.get("primary_metrics", {})) != set(tasks) or any(int(directions.get(task, 0)) not in {-1, 1} for task in tasks):
        raise TuningConfigurationError("Primary metrics and directions are required for every task")
    folds = dict(raw.get("tuning_folds", {}))
    if int(folds.get("folds", 0)) != 5 or folds.get("expanding_window") is not True or folds.get("purge_label_windows") is not True:
        raise TuningConfigurationError("tuning_v1 requires five expanding, purged folds")
    if tuple(folds.get("source_splits", ())) != ("train", "validation") or "test" not in folds.get("excluded_splits", ()):
        raise TuningConfigurationError("Tuning folds must use train+validation and exclude test")
    if int(folds.get("embargo_days", 0)) < 1:
        raise TuningConfigurationError("A positive tuning-fold embargo is required")
    thresholds = dict(raw.get("binary_thresholds", {}))
    values = tuple(float(value) for value in thresholds.get("values", ()))
    if not values or values != tuple(sorted(set(values))) or any(value <= 0 or value >= 1 for value in values):
        raise TuningConfigurationError("Binary thresholds must be unique, sorted, and between zero and one")
    if not 0 < float(thresholds.get("minimum_coverage", 0)) <= 1:
        raise TuningConfigurationError("minimum_coverage must be in (0, 1]")
    smoke = {key: int(value) for key, value in raw.get("smoke", {}).items()}
    if int(smoke.get("trial_limit", 0)) <= 0:
        raise TuningConfigurationError("Positive smoke trial_limit is required")
    out = _path(artifacts_root) if artifacts_root else _path(raw["artifacts_root"])
    return TuningConfig("tuning_v1", base, ds_root, out, int(raw.get("random_seed", 42)), tasks, trials, selection, folds, thresholds, smoke, raw)
