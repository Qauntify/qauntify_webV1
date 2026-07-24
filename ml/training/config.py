"""Strict shared configuration for local and Colab training."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ml.data.load_dataset import PROJECT_ROOT

TASKS = ("binary", "multiclass", "regression")


class TrainingRunConfigurationError(ValueError): pass


@dataclass(frozen=True)
class ExperimentConfig:
    version: str; model_family: str; dataset_root: Path; manifest_path: Path; artifacts_root: Path
    random_seed: int; tasks: tuple[str, ...]; parameters: dict; evaluation: dict; smoke: dict; raw: dict


def _path(value, *, base=PROJECT_ROOT):
    path = Path(str(value)); return path.resolve() if path.is_absolute() else (base / path).resolve()


def load_experiment_config(path: Path, *, dataset_root: Path | None = None, artifacts_root: Path | None = None):
    import yaml
    path = _path(path); raw = yaml.safe_load(path.read_text("utf-8"))
    family = raw.get("model_family")
    if family not in {"baseline", "catboost"}: raise TrainingRunConfigurationError("model_family must be baseline or catboost")
    expected_version = f"{family}_v1"
    if raw.get("version") != expected_version: raise TrainingRunConfigurationError(f"version must be {expected_version}")
    tasks = tuple(raw.get("tasks", ()))
    if not tasks or len(tasks) != len(set(tasks)) or not set(tasks).issubset(TASKS): raise TrainingRunConfigurationError("Invalid task list")
    seed = int(raw.get("random_seed", 42))
    smoke = {key: int(value) for key, value in raw.get("smoke", {}).items()}
    if any(smoke.get(key, 0) <= 0 for key in ("train_rows", "validation_rows", "test_rows")): raise TrainingRunConfigurationError("Positive smoke row limits are required")
    parameters = dict(raw.get(family, {}))
    evaluation = dict(raw.get("evaluation", {}))
    if evaluation.get("walk_forward") is not True: raise TrainingRunConfigurationError("All five protected walk-forward folds are required")
    if int(evaluation.get("calibration_bins", 0)) < 2 or int(evaluation.get("score_buckets", 0)) < 2: raise TrainingRunConfigurationError("Evaluation bins must be at least two")
    if int(evaluation.get("shap_sample_rows", -1)) < 0: raise TrainingRunConfigurationError("SHAP sample size cannot be negative")
    if family == "catboost":
        required = {"iterations","depth","learning_rate","loss_binary","loss_multiclass","loss_regression","early_stopping_rounds","snapshot_interval_seconds"}
        if missing := sorted(required-set(parameters)): raise TrainingRunConfigurationError(f"Missing CatBoost parameters: {missing}")
    else:
        if parameters.get("classifier_strategy") not in {"prior","most_frequent","stratified"}: raise TrainingRunConfigurationError("Invalid baseline classifier strategy")
        if parameters.get("regressor_strategy") not in {"mean","median"}: raise TrainingRunConfigurationError("Invalid baseline regressor strategy")
    ds_root = _path(dataset_root) if dataset_root else _path(raw["training_dataset_root"])
    manifest = ds_root / "training_manifest.json" if dataset_root else _path(raw["training_manifest_path"])
    out = _path(artifacts_root) if artifacts_root else _path(raw["artifacts_root"])
    return ExperimentConfig(expected_version, family, ds_root, manifest, out, seed, tasks, parameters, evaluation, smoke, raw)
