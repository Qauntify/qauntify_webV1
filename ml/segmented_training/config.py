"""Strict configuration for training_v2_segmented_temporal."""
from dataclasses import dataclass
from pathlib import Path

from ml.data.load_dataset import PROJECT_ROOT
from ml.training.config import ExperimentConfig, load_experiment_config


class SegmentedTrainingConfigurationError(ValueError): pass


@dataclass(frozen=True)
class SegmentedTrainingConfig:
    version: str; base: ExperimentConfig; dataset_root: Path; artifacts_root: Path; random_seed: int
    tasks: tuple[str, ...]; segments: tuple[dict, ...]; inner: dict; thresholds: dict; safeguards: dict; smoke: dict; raw: dict


def _path(value):
    path=Path(str(value)); return path.resolve() if path.is_absolute() else (PROJECT_ROOT/path).resolve()


def load_segmented_config(path, *, dataset_root=None, artifacts_root=None):
    import yaml
    raw=yaml.safe_load(_path(path).read_text("utf-8"))
    if raw.get("version")!="training_v2_segmented_temporal": raise SegmentedTrainingConfigurationError("Invalid experiment version")
    root=_path(dataset_root) if dataset_root else _path(raw["training_dataset_root"])
    base=load_experiment_config(_path(raw["base_config"]),dataset_root=root)
    tasks=tuple(raw.get("tasks",()))
    if tasks != ("binary","regression"): raise SegmentedTrainingConfigurationError("Binary and regression tasks are required")
    segments=tuple(dict(item) for item in raw.get("segments",()))
    if {item.get("id") for item in segments}!={"ict_fvg_m5","sr_zone_m15"}: raise SegmentedTrainingConfigurationError("Required segment definitions are missing")
    inner=dict(raw.get("inner_calibration",{})); guards=dict(raw.get("safeguards",{})); thresholds=dict(raw.get("thresholds",{}))
    if int(raw.get("outer_folds",0))!=5 or int(inner.get("folds",0))!=3 or int(inner.get("embargo_days",0))<1:
        raise SegmentedTrainingConfigurationError("Five outer folds and three embargoed inner folds are required")
    if tuple(inner.get("methods",())) != ("sigmoid","isotonic"): raise SegmentedTrainingConfigurationError("Calibration methods must be sigmoid and isotonic")
    if float(thresholds.get("start",0))!=.4 or float(thresholds.get("stop",0))!=.6 or float(thresholds.get("step",0))!=.005:
        raise SegmentedTrainingConfigurationError("Threshold contract must be 0.40..0.60 step 0.005")
    required={"minimum_coverage","minimum_positive_folds","minimum_candidates_per_fold","maximum_fold_candidate_share","maximum_year_profit_share","primary_cost_r","sensitivity_costs_r"}
    if required-set(guards): raise SegmentedTrainingConfigurationError("Incomplete safeguard contract")
    if int(guards["minimum_candidates_per_fold"])!=100 or float(guards["primary_cost_r"])!=.02 or tuple(guards["sensitivity_costs_r"])!=(.03,.05):
        raise SegmentedTrainingConfigurationError("Approved count and cost assumptions changed")
    smoke={key:int(value) for key,value in raw.get("smoke",{}).items()}
    return SegmentedTrainingConfig(raw["version"],base,root,_path(artifacts_root) if artifacts_root else _path(raw["artifacts_root"]),
        int(raw.get("random_seed",42)),tasks,segments,inner,thresholds,guards,smoke,raw)
