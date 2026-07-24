import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from ml.training.config import load_experiment_config
from ml.training.data import TrainingData
from ml.training.runner import run_experiment
from signals.ml.registry import sha256_file


def test_baseline_and_catboost_configs_are_shared_and_strict():
    baseline=load_experiment_config(Path("ml/configs/baseline_v1.yaml"))
    catboost=load_experiment_config(Path("ml/configs/catboost_v1.yaml"))
    assert baseline.tasks == catboost.tasks == ("binary","multiclass","regression")
    assert baseline.dataset_root == catboost.dataset_root
    assert baseline.evaluation["walk_forward"] is catboost.evaluation["walk_forward"] is True
    assert catboost.parameters["iterations"] == 1000
    assert catboost.smoke["iterations"] == 10


def _training_data():
    frames={}
    for split,offset in (("train",0),("validation",20),("test",40)):
        binary=np.array([0,1]*10); multiclass=np.array(["sl_before_tp1","tp3_hit"]*10)
        frames[split]=pd.DataFrame({"candidate_id":[f"{split}-{i}" for i in range(20)],
            "candidate_timestamp":pd.date_range("2020-01-01",periods=20,freq="h",tz="UTC")+pd.Timedelta(days=offset),
            "strategy_name":"ema_cross","timeframe":"H1","direction":"long","year":2020,
            "numeric":np.arange(20,dtype=float),"category":["a","b"]*10,
            "target_binary_success":binary,"target_outcome_class":multiclass,"target_net_realized_r":np.where(binary,1.0,-1.0)})
    manifest={"training_dataset_id":"training:test","checksum":"abc","model_feature_columns":["numeric","category"],
              "target_columns":["target_binary_success","target_outcome_class","target_net_realized_r"]}
    walk={fold:{"train":frames["train"],"validation":frames["validation"]} for fold in range(1,6)}
    return TrainingData(frames,("numeric","category"),("category",),manifest,walk)


def test_baseline_runner_saves_evaluation_artifacts_and_resumes(monkeypatch,tmp_path):
    pytest.importorskip("sklearn"); pytest.importorskip("joblib")
    config=SimpleNamespace(version="baseline_v1",model_family="baseline",parameters={"classifier_strategy":"prior","regressor_strategy":"median"},
        random_seed=42,tasks=("binary","multiclass","regression"),raw={"version":"baseline_v1"},dataset_root=tmp_path,
        evaluation={"calibration_bins":5,"score_buckets":5,"shap_sample_rows":0},smoke={})
    monkeypatch.setattr("ml.training.runner.load_verified_training_data",lambda config,smoke:_training_data())
    experiment=tmp_path/"experiment"
    manifest=run_experiment(config,experiment_dir=experiment,smoke=False)
    assert manifest["status"] == "complete"
    metrics=json.loads((experiment/"metrics.json").read_text())
    assert set(metrics["main"]) == {"binary","multiclass","regression"}
    assert len(manifest["walk_forward_row_counts"]) == 5 and manifest["completed_jobs"] == 18
    assert all((experiment/"models"/"main"/f"{task}.joblib").is_file() for task in config.tasks)
    assert all((experiment/"predictions"/"main"/f"{task}_test.parquet").is_file() for task in config.tasks)
    assert all((experiment/"predictions"/"fold_01"/f"{task}_validation.parquet").is_file() for task in config.tasks)
    checksums=json.loads((experiment/"artifact_checksums.json").read_text())
    assert "experiment_manifest.json" in checksums and "feature_contract.json" in checksums
    assert all(sha256_file(experiment/name) == checksum for name,checksum in checksums.items())
    resumed=run_experiment(config,experiment_dir=experiment,smoke=False,resume=True)
    assert resumed["tasks"] == list(config.tasks)


def test_resume_rejects_changed_configuration(monkeypatch,tmp_path):
    config=SimpleNamespace(version="baseline_v1",model_family="baseline",parameters={},random_seed=42,tasks=("binary",),raw={"a":1},dataset_root=tmp_path,evaluation={},smoke={})
    experiment=tmp_path/"experiment"; experiment.mkdir()
    (experiment/"run_state.json").write_text(json.dumps({"config_identity":"wrong","completed_tasks":[]}),"utf-8")
    with pytest.raises(ValueError,match="does not match"):
        run_experiment(config,experiment_dir=experiment,resume=True)


def test_colab_notebook_delegates_to_shared_cli():
    notebook=json.loads(Path("ml/notebooks/training_v1_colab.ipynb").read_text("utf-8"))
    source="\n".join("".join(cell.get("source",[])) for cell in notebook["cells"])
    code_source="\n".join("".join(cell.get("source",[])) for cell in notebook["cells"] if cell.get("cell_type")=="code")
    assert "drive.mount('/content/drive')" in source and "requirements-training.txt" in source
    assert "git', 'clone'" in source and "ml.training.verify" in source
    assert source.count("ml.training.cli") == 2 and "ml.training.compare" in source and "--resume" in source
    assert "--smoke" not in code_source
    assert "CatBoostClassifier(" not in source and "DummyClassifier(" not in source
