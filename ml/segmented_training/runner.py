"""Resume-aware segmented CatBoost training with past-only calibration."""
from __future__ import annotations
import hashlib, json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from ml.segmented_training.calibration import fit_temporal_calibrator
from ml.segmented_training.data import assert_outer_isolation, build_inner_calibration_folds, filter_segment
from ml.thresholding.calibration import apply_calibrator
from ml.thresholding.metrics import policy_metrics, safeguards
from ml.training.data import TARGET_BY_TASK, load_verified_training_data
from ml.training.runner import _baseline, _catboost, _environment, _git_commit, _predict, _save_model, _sha256, _write_json


def _identity(config, smoke):
    return hashlib.sha256(json.dumps({"raw":config.raw,"dataset":str(config.dataset_root),"smoke":smoke,"commit":_git_commit()},sort_keys=True).encode()).hexdigest()


def _base(config, smoke):
    values=dict(config.base.smoke)
    if smoke: values["iterations"]=config.smoke["iterations"]
    return replace(config.base,random_seed=config.random_seed,tasks=config.tasks,smoke=values)


def _binary_score(model, frame, data):
    _,probabilities,classes=_predict(model,"catboost","binary",frame,data.feature_columns)
    return probabilities[:,list(classes).index(1)]


def _baseline_predictions(task, train, validation, config):
    parameters={"classifier_strategy":"prior","regressor_strategy":"mean"}; model=_baseline(task,parameters,train[TARGET_BY_TASK[task]],config.random_seed)
    prediction,probabilities,classes=_predict(model,"baseline",task,validation,())
    score=prediction if task=="regression" else probabilities[:,list(classes).index(1)]
    return score


def _run_outer(config, data, root, segment, fold, smoke):
    outer=data.walk_forward[fold]; train=filter_segment(outer["train"],segment); validation=filter_segment(outer["validation"],segment)
    if smoke:
        train=train.tail(config.smoke["train_rows_per_segment"]); validation=validation.head(config.smoke["validation_rows_per_segment"])
    if train.empty or validation.empty: raise ValueError(f"Segment {segment['id']} fold {fold} is empty")
    inner=build_inner_calibration_folds(train,config.inner); assert_outer_isolation(inner,validation)
    nested=[]; base=_base(config,smoke)
    for item in inner:
        slug=f"{segment['id']}__outer_{fold:02d}__inner_{item['fold']:02d}__binary"
        model=_catboost("binary",base,root,slug,item["train"],item["validation"],data.feature_columns,data.categorical_columns,smoke)
        score=_binary_score(model,item["validation"],data)
        output=item["validation"][["candidate_id","target_binary_success"]].copy(); output["raw_probability"]=score; nested.append(output)
    calibration_frame=pd.concat(nested,ignore_index=True)
    method,calibrator,calibration_report=fit_temporal_calibrator(calibration_frame,config.inner)
    cal_path=root/"calibrators"/segment["id"]/f"fold_{fold:02d}.joblib"; cal_path.parent.mkdir(parents=True,exist_ok=True); joblib.dump(calibrator,cal_path)
    _write_json(cal_path.with_suffix(".json"),{**calibration_report,"fit_candidate_ids_sha256":hashlib.sha256("\n".join(sorted(calibration_frame.candidate_id.astype(str))).encode()).hexdigest(),
        "outer_validation_overlap":0,"fit_timestamp_max":max(item["validation"].candidate_timestamp.max() for item in inner).isoformat(),
        "outer_validation_timestamp_min":validation.candidate_timestamp.min().isoformat()})

    models={}
    for task in config.tasks:
        slug=f"{segment['id']}__outer_{fold:02d}__{task}"
        model=_catboost(task,base,root,slug,train,validation,data.feature_columns,data.categorical_columns,smoke); models[task]=model
        _save_model(model,"catboost",root/"models"/segment["id"]/f"fold_{fold:02d}"/f"{task}.cbm")
    raw=_binary_score(models["binary"],validation,data); calibrated=apply_calibrator(calibrator,method,raw)
    regression,_,_=_predict(models["regression"],"catboost","regression",validation,data.feature_columns)
    output=validation[["candidate_id","candidate_timestamp","strategy_name","timeframe","direction","target_binary_success","target_net_realized_r"]].copy()
    output["fold"]=fold; output["raw_probability"]=raw; output["calibrated_probability"]=calibrated; output["predicted_regression_r"]=regression
    output["baseline_binary_probability"]=_baseline_predictions("binary",train,validation,config)
    output["baseline_regression_r"]=_baseline_predictions("regression",train,validation,config)
    path=root/"predictions"/segment["id"]/f"fold_{fold:02d}.parquet"; path.parent.mkdir(parents=True,exist_ok=True); output.to_parquet(path,index=False,compression="zstd")
    return {"train_rows":len(train),"validation_rows":len(validation),"inner_calibration_rows":len(calibration_frame),"calibration":calibration_report}


def _threshold_values(config):
    values=[]; value=float(config.thresholds["start"])
    while value<=float(config.thresholds["stop"])+1e-9: values.append(round(value,3)); value+=float(config.thresholds["step"])
    return values


def _policy_table(frame,config):
    rows=[]; masks={}; guards=config.safeguards
    for threshold in _threshold_values(config):
        mask=(frame.calibrated_probability>=threshold)&(frame.predicted_regression_r>0); metrics=policy_metrics(frame,mask,cost_r=float(guards["primary_cost_r"])); checks,passed=safeguards(metrics,
            minimum_coverage=float(guards["minimum_coverage"]),minimum_positive_folds=int(guards["minimum_positive_folds"]),minimum_count_per_fold=int(guards["minimum_candidates_per_fold"]))
        counts=np.asarray([item["candidate_count"] for item in metrics["folds"].values()]); total=max(int(counts.sum()),1); fold_share=float(counts.max()/total)
        selected=frame[mask].copy(); selected["after_cost_r"]=selected.target_net_realized_r-float(guards["primary_cost_r"]); selected["year"]=pd.to_datetime(selected.candidate_timestamp,utc=True).dt.year
        yearly=selected.groupby("year").after_cost_r.sum(); positive=yearly[yearly>0]; year_share=float(positive.max()/positive.sum()) if len(positive) and positive.sum()>0 else 1.0
        extra={"maximum_fold_candidate_share":fold_share,"maximum_year_profit_share":year_share,
            "fold_concentration_passed":fold_share<=float(guards["maximum_fold_candidate_share"]),
            "year_concentration_passed":year_share<=float(guards["maximum_year_profit_share"])}
        eligible=passed and extra["fold_concentration_passed"] and extra["year_concentration_passed"]
        row={"threshold":threshold,**{k:v for k,v in metrics.items() if k!="folds"},**checks,**extra,"eligible":eligible,"folds":metrics["folds"]}; rows.append(row); masks[threshold]=mask
    rows.sort(key=lambda row:(-int(row["eligible"]),-row["positive_folds"],-row["minimum_fold_candidate_count"],-row["mean_r"],row["threshold"]))
    winner=next((row for row in rows if row["eligible"]),None)
    sensitivity={}
    if winner:
        for cost in (guards["primary_cost_r"],*guards["sensitivity_costs_r"]): sensitivity[str(cost)]=policy_metrics(frame,masks[winner["threshold"]],cost_r=float(cost))
    return rows,winner,sensitivity


def run_segmented_training(config,*,experiment_dir,smoke=False,resume=False):
    root=Path(experiment_dir).resolve(); root.mkdir(parents=True,exist_ok=True); state_path=root/"run_state.json"; identity=_identity(config,smoke)
    if state_path.exists():
        state=json.loads(state_path.read_text("utf-8"))
        if not resume: raise FileExistsError("Experiment exists; use --resume")
        if state.get("config_identity")!=identity: raise ValueError("Resume identity mismatch")
    else: state={"config_identity":identity,"status":"running","completed_jobs":[],"created_at":datetime.now(timezone.utc).isoformat()}; _write_json(state_path,state)
    data=load_verified_training_data(_base(config,False),smoke=False)
    results={}
    for segment in config.segments:
        results[segment["id"]]={}
        for fold in range(1,6):
            job=f"{segment['id']}/fold_{fold:02d}"
            if job not in state["completed_jobs"]:
                results[segment["id"]][str(fold)]=_run_outer(config,data,root,segment,fold,smoke); state["completed_jobs"].append(job); _write_json(state_path,state)
    reports={}; locked={}
    for segment in config.segments:
        frame=pd.concat([pd.read_parquet(path) for path in sorted((root/"predictions"/segment["id"]).glob("fold_*.parquet"))],ignore_index=True)
        rows,winner,sensitivity=_policy_table(frame,config); reports[segment["id"]]={"rows":len(frame),"winner":winner,"cost_sensitivity":sensitivity}; _write_json(root/"policy_tables"/f"{segment['id']}.json",rows)
        if winner: locked[segment["id"]]=winner
    report={"version":config.version,"created_at":datetime.now(timezone.utc).isoformat(),"selection_data":"nested past-only and outer validation only; test excluded",
        "segments":reports,"locked_segment_count":len(locked),"test_rows_used":0,"deployment_status":"not_approved"}; _write_json(root/"training_v2_report.json",report)
    lines=["# training_v2 segmented temporal report","","- Test rows used: `0`",f"- Locked segment policies: `{len(locked)}`",""]
    for segment,values in reports.items(): lines += [f"## {segment}","",f"- Validation rows: `{values['rows']}`",f"- Policy passed: `{values['winner'] is not None}`",""]
    (root/"training_v2_report.md").write_text("\n".join(lines),"utf-8")
    state.update({"status":"complete","completed_at":datetime.now(timezone.utc).isoformat()}); _write_json(state_path,state); _write_json(root/"environment.json",_environment())
    manifest={"version":config.version,"status":"complete","smoke":smoke,"training_dataset_id":data.manifest["training_dataset_id"],"training_dataset_checksum":data.manifest["checksum"],
        "segments":[item["id"] for item in config.segments],"outer_folds":5,"inner_calibration_folds":3,"completed_jobs":len(state["completed_jobs"]),"expected_jobs":10,
        "test_rows_used":0,"locked_segment_count":len(locked),"deployment_status":"not_approved"}; _write_json(root/"training_v2_manifest.json",manifest)
    files=sorted(path for path in root.rglob("*") if path.is_file() and path.name!="artifact_checksums.json"); _write_json(root/"artifact_checksums.json",{str(path.relative_to(root)).replace("\\","/"):_sha256(path) for path in files})
    return manifest
