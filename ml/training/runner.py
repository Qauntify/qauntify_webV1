"""Shared, resume-aware baseline and CatBoost experiment runner."""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from ml.training.data import TARGET_BY_TASK, load_verified_training_data
from ml.training.diagnostics import analyze_predictions, build_prediction_frame, calibration_table, feature_diagnostics
from ml.training.evaluation import evaluate


def _write_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);temporary=path.with_suffix(path.suffix+".tmp");temporary.write_text(json.dumps(value,indent=2,sort_keys=True)+"\n","utf-8")
    for attempt in range(6):
        try:temporary.replace(path);return
        except PermissionError:
            if attempt==5:raise
            time.sleep(0.1*(attempt+1))


def _log(path,event,**values):
    record={"timestamp":datetime.now(timezone.utc).isoformat(),"event":event,**values}; path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("a",encoding="utf-8") as stream: stream.write(json.dumps(record,sort_keys=True)+"\n")


def _sha256(path):
    digest=hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b""): digest.update(chunk)
    return digest.hexdigest()


def _git_commit():
    try:return subprocess.run(["git","rev-parse","HEAD"],capture_output=True,text=True,check=True).stdout.strip()
    except Exception:return None


def _config_identity(config,smoke):
    payload=json.dumps({"raw":config.raw,"dataset":str(config.dataset_root),"smoke":smoke,"code_commit":_git_commit()},sort_keys=True,separators=(",",":"));return hashlib.sha256(payload.encode()).hexdigest()


def _environment():
    packages={}
    for name in ("numpy","pandas","pyarrow","scikit-learn","catboost","joblib","scipy"):
        try:packages[name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:packages[name]=None
    return {"python":platform.python_version(),"platform":platform.platform(),"packages":packages}


def _baseline(task,parameters,y_train,seed):
    y=np.asarray(y_train,dtype="float64" if task=="regression" else ("int64" if task=="binary" else "str"));X=np.zeros((len(y),1))
    if task=="regression":
        from sklearn.dummy import DummyRegressor
        return DummyRegressor(strategy=parameters["regressor_strategy"]).fit(X,y)
    from sklearn.dummy import DummyClassifier
    return DummyClassifier(strategy=parameters["classifier_strategy"],random_state=seed).fit(X,y)


def _catboost(task,config,experiment,job_slug,train,validation,features,categorical,smoke):
    from catboost import CatBoostClassifier,CatBoostRegressor,Pool
    params=config.parameters;iterations=config.smoke.get("iterations",10) if smoke else int(params["iterations"])
    train_dir=experiment/"logs"/"catboost"/job_slug;snapshot=experiment/"snapshots"/f"{job_slug}.snapshot";train_dir.mkdir(parents=True,exist_ok=True);snapshot.parent.mkdir(parents=True,exist_ok=True)
    common={"iterations":iterations,"depth":int(params["depth"]),"learning_rate":float(params["learning_rate"]),"l2_leaf_reg":float(params.get("l2_leaf_reg",3)),
        "random_seed":config.random_seed,"early_stopping_rounds":min(int(params["early_stopping_rounds"]),max(iterations//3,1)),"thread_count":int(params.get("thread_count",-1)),
        "task_type":params.get("task_type","CPU"),"verbose":int(params.get("verbose",50)),"allow_writing_files":True,"train_dir":str(train_dir),
        "save_snapshot":True,"snapshot_file":str(snapshot),"snapshot_interval":int(params["snapshot_interval_seconds"]),"use_best_model":True}
    target=TARGET_BY_TASK[task];dtype="float64" if task=="regression" else ("int64" if task=="binary" else "str")
    train_pool=Pool(train[list(features)],np.asarray(train[target],dtype=dtype),cat_features=list(categorical),feature_names=list(features))
    validation_pool=Pool(validation[list(features)],np.asarray(validation[target],dtype=dtype),cat_features=list(categorical),feature_names=list(features))
    if task=="regression":model=CatBoostRegressor(loss_function=params["loss_regression"],eval_metric=params.get("eval_regression","RMSE"),**common)
    elif task=="binary":model=CatBoostClassifier(loss_function=params["loss_binary"],eval_metric=params.get("eval_binary","AUC"),**common)
    else:model=CatBoostClassifier(loss_function=params["loss_multiclass"],eval_metric=params.get("eval_multiclass","MultiClass"),**common)
    model.fit(train_pool,eval_set=validation_pool);return model


def _predict(model,family,task,frame,features):
    X=np.zeros((len(frame),1)) if family=="baseline" else frame[list(features)];prediction=np.asarray(model.predict(X)).reshape(-1)
    probabilities=None;classes=getattr(model,"classes_",None)
    if task!="regression":probabilities=np.asarray(model.predict_proba(X));prediction=prediction.astype(int) if task=="binary" else prediction.astype(str)
    return prediction,probabilities,classes


def _save_model(model,family,path):
    path.parent.mkdir(parents=True,exist_ok=True)
    if family=="baseline":
        import joblib;joblib.dump(model,path)
    else:model.save_model(str(path),format="cbm")


def _run_job(config,data,experiment,scope,task,frames,smoke,metrics,analysis,log_path):
    job_id=f"{scope}/{task}";job_slug=job_id.replace("/","__");train=frames["train"];validation=frames["validation"];target=TARGET_BY_TASK[task]
    _log(log_path,"job_started",job_id=job_id,train_rows=len(train),validation_rows=len(validation))
    model=_baseline(task,config.parameters,train[target],config.random_seed) if config.model_family=="baseline" else _catboost(task,config,experiment,job_slug,train,validation,data.feature_columns,data.categorical_columns,smoke)
    suffix="joblib" if config.model_family=="baseline" else "cbm";_save_model(model,config.model_family,experiment/"models"/scope/f"{task}.{suffix}")
    job_metrics={};job_analysis={}
    for split,frame in frames.items():
        prediction,probabilities,classes=_predict(model,config.model_family,task,frame,data.feature_columns)
        job_metrics[split]=evaluate(task,frame[target].to_numpy(),prediction,probabilities,classes)
        output=build_prediction_frame(task,frame,prediction,probabilities,classes,split)
        # Main predictions retain all splits. Fold exports retain only out-of-time validation predictions.
        if scope=="main" or split=="validation":
            prediction_path=experiment/"predictions"/scope/f"{task}_{split}.parquet";prediction_path.parent.mkdir(parents=True,exist_ok=True);output.to_parquet(prediction_path,index=False,compression="zstd")
        if scope=="main" or split=="validation":
            diagnostics=analyze_predictions(task,output,classes,int(config.evaluation["calibration_bins"]));job_analysis[split]=diagnostics
            calibration=calibration_table(task,output,int(config.evaluation["calibration_bins"]));cal_path=experiment/"calibration"/scope/f"{task}_{split}.parquet";cal_path.parent.mkdir(parents=True,exist_ok=True);calibration.to_parquet(cal_path,index=False,compression="zstd")
    if scope=="main":
        if config.model_family=="catboost":job_analysis["features"]=feature_diagnostics(model,task,validation,data.feature_columns,data.categorical_columns,int(config.evaluation["shap_sample_rows"]))
        else:job_analysis["features"]={"feature_importance":[],"shap_summary":None,"reason":"Dummy baselines do not use input features"}
    metrics[scope][task]=job_metrics;analysis[scope][task]=job_analysis
    _log(log_path,"job_completed",job_id=job_id,metrics=job_metrics)


def run_experiment(config,*,experiment_dir:Path,smoke=False,resume=False):
    experiment=experiment_dir.resolve();experiment.mkdir(parents=True,exist_ok=True);identity=_config_identity(config,smoke);state_path=experiment/"run_state.json";log_path=experiment/"logs"/"training.jsonl"
    if state_path.exists():
        state=json.loads(state_path.read_text("utf-8"))
        if not resume:raise FileExistsError(f"Experiment exists: {experiment}; use --resume")
        if state.get("config_identity")!=identity:raise ValueError("Resume config does not match existing experiment")
    else:state={"config_identity":identity,"status":"running","completed_jobs":[],"created_at":datetime.now(timezone.utc).isoformat()};_write_json(state_path,state)
    state.setdefault("completed_jobs",[]);data=load_verified_training_data(config,smoke=smoke)
    import yaml
    (experiment/"config_resolved.yaml").write_text(yaml.safe_dump(config.raw,sort_keys=True),"utf-8");_write_json(experiment/"environment.json",_environment())
    _write_json(experiment/"feature_contract.json",{"training_dataset_id":data.manifest["training_dataset_id"],"training_dataset_checksum":data.manifest["checksum"],"feature_columns":list(data.feature_columns),"categorical_columns":list(data.categorical_columns),"targets":TARGET_BY_TASK,"walk_forward_folds":5,"test_usage":"evaluation_only_after_fitting; never used for model or threshold selection"})
    metrics_path=experiment/"metrics.json";analysis_path=experiment/"evaluation_details.json"
    metrics=json.loads(metrics_path.read_text("utf-8")) if metrics_path.exists() else {"main":{},**{f"fold_{fold:02d}":{} for fold in range(1,6)}}
    analysis=json.loads(analysis_path.read_text("utf-8")) if analysis_path.exists() else {"main":{},**{f"fold_{fold:02d}":{} for fold in range(1,6)}}
    jobs=[("main",task,data.frames) for task in config.tasks]
    jobs.extend((f"fold_{fold:02d}",task,data.walk_forward[fold]) for fold in range(1,6) for task in config.tasks)
    for scope,task,frames in jobs:
        job_id=f"{scope}/{task}"
        if job_id in state["completed_jobs"]:continue
        _run_job(config,data,experiment,scope,task,frames,smoke,metrics,analysis,log_path)
        _write_json(metrics_path,metrics);_write_json(analysis_path,analysis);state["completed_jobs"].append(job_id);state["last_completed_at"]=datetime.now(timezone.utc).isoformat();_write_json(state_path,state)
    state["status"]="complete";state["completed_at"]=datetime.now(timezone.utc).isoformat();_write_json(state_path,state)
    run_manifest={"experiment_version":config.version,"model_family":config.model_family,"smoke":smoke,"status":"complete","training_dataset_id":data.manifest["training_dataset_id"],
        "training_dataset_checksum":data.manifest["checksum"],"code_commit":_git_commit(),"tasks":list(config.tasks),"main_row_counts":{key:len(value) for key,value in data.frames.items()},
        "walk_forward_row_counts":{f"fold_{fold:02d}":{key:len(value) for key,value in frames.items()} for fold,frames in data.walk_forward.items()},
        "completed_jobs":len(state["completed_jobs"]),"expected_jobs":18,"test_policy":"untouched until final evaluation; not used for selection or thresholds","artifact_count":0,"completed_at":state["completed_at"]}
    run_manifest["artifact_count"]=sum(1 for path in experiment.rglob("*") if path.is_file() and path.name not in {"artifact_checksums.json","experiment_manifest.json"})+1;_write_json(experiment/"experiment_manifest.json",run_manifest)
    artifact_files=tuple(sorted(path for path in experiment.rglob("*") if path.is_file() and path.name!="artifact_checksums.json"));_write_json(experiment/"artifact_checksums.json",{str(path.relative_to(experiment)).replace("\\","/"):_sha256(path) for path in artifact_files})
    return run_manifest
