"""Strict threshold_v2 configuration and assumption audit."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ml.data.load_dataset import PROJECT_ROOT
from ml.training.config import ExperimentConfig, load_experiment_config


class ThresholdConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class ThresholdConfig:
    version: str
    base: ExperimentConfig
    dataset_root: Path
    tuning_root: Path
    output_root: Path
    minimum_count_per_fold: int | None
    trading_cost_r: float | None
    cost_sensitivity_r: tuple[float, ...]
    calibration: dict
    threshold_search: dict
    combined_filters: dict
    segment_dimensions: tuple[str, ...]
    threshold_v1_probability: float
    raw: dict

    @property
    def missing_assumptions(self):
        missing = []
        if self.minimum_count_per_fold is None:
            missing.append("minimum_accepted_candidates_per_fold")
        if self.trading_cost_r is None:
            missing.append("trading_cost_r")
        return tuple(missing)


def _path(value):
    path = Path(str(value))
    return path.resolve() if path.is_absolute() else (PROJECT_ROOT / path).resolve()


def load_threshold_config(path: Path, *, dataset_root=None, tuning_root=None, output_root=None):
    import yaml

    raw = yaml.safe_load(_path(path).read_text("utf-8"))
    if raw.get("version") != "threshold_v2":
        raise ThresholdConfigurationError("version must be threshold_v2")
    ds_root = _path(dataset_root) if dataset_root else _path(raw["training_dataset_root"])
    base = load_experiment_config(_path(raw["base_config"]), dataset_root=ds_root)
    calibration = dict(raw.get("calibration", {}))
    if tuple(calibration.get("methods", ())) != ("sigmoid", "isotonic") or int(calibration.get("cross_fit_folds", 0)) != 5:
        raise ThresholdConfigurationError("threshold_v2 requires five-fold sigmoid and isotonic calibration")
    search = dict(raw.get("threshold_search", {}))
    if not (float(search.get("start", 0)) == 0.50 and float(search.get("stop", 0)) == 0.56 and 0 < float(search.get("step", 0)) <= 0.01):
        raise ThresholdConfigurationError("Threshold search must cover 0.50 through 0.56 with a fine positive step")
    if not 0 < float(search.get("minimum_coverage", 0)) <= 1 or int(search.get("minimum_positive_folds", 0)) not in range(1, 6):
        raise ThresholdConfigurationError("Invalid economic safeguards")
    count = raw.get("minimum_accepted_candidates_per_fold")
    cost = raw.get("trading_cost_r")
    if count is not None and int(count) <= 0:
        raise ThresholdConfigurationError("minimum candidate count must be positive")
    if cost is not None and float(cost) < 0:
        raise ThresholdConfigurationError("trading cost cannot be negative")
    sensitivity = tuple(float(value) for value in raw.get("cost_sensitivity_r", ()))
    if sensitivity != (0.03, 0.05) or any(value <= float(cost or 0) for value in sensitivity):
        raise ThresholdConfigurationError("Cost sensitivity must be fixed at 0.03 R and 0.05 R above the primary cost")
    dimensions = tuple(raw.get("segment_dimensions", ()))
    if dimensions != ("strategy_name", "timeframe", "direction", "confidence_bucket"):
        raise ThresholdConfigurationError("Required segment dimensions are missing")
    return ThresholdConfig("threshold_v2", base, ds_root, _path(tuning_root or raw["tuning_root"]), _path(output_root or raw["output_root"]),
                           int(count) if count is not None else None, float(cost) if cost is not None else None, sensitivity,
                           calibration, search, dict(raw.get("combined_filters", {})), dimensions,
                           float(raw.get("threshold_v1_probability", 0.5)), raw)


def require_assumptions(config: ThresholdConfig):
    if config.missing_assumptions:
        raise ThresholdConfigurationError("Missing required assumptions: " + ", ".join(config.missing_assumptions))
