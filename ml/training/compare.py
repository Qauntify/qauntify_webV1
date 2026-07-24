"""Baseline-versus-CatBoost comparison using validation and walk-forward evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime,timezone
from pathlib import Path

import numpy as np


PRIMARY={"binary":("roc_auc",1),"multiclass":("macro_f1",1),"regression":("rmse",-1)}


def _read_experiment(root):
    manifest=json.loads((root/"experiment_manifest.json").read_text("utf-8"));metrics=json.loads((root/"metrics.json").read_text("utf-8"));details=json.loads((root/"evaluation_details.json").read_text("utf-8"))
    if manifest.get("status")!="complete" or int(manifest.get("completed_jobs",0))!=18:raise ValueError(f"Incomplete experiment: {root}")
    return manifest,metrics,details


def _summarize_task(task,baseline,catboost):
    metric,direction=PRIMARY[task];main={}
    for split in ("train","validation","test"):
        b=baseline["main"][task][split].get(metric);c=catboost["main"][task][split].get(metric)
        main[split]={"baseline":b,"catboost":c,"catboost_minus_baseline_oriented":direction*(c-b)}
    folds=[]
    for fold in range(1,6):
        scope=f"fold_{fold:02d}";b=baseline[scope][task]["validation"].get(metric);c=catboost[scope][task]["validation"].get(metric)
        folds.append({"fold":fold,"baseline":b,"catboost":c,"catboost_improvement_oriented":direction*(c-b),
                      "catboost_train":catboost[scope][task]["train"].get(metric),"catboost_validation":c})
    cat_values=np.asarray([row["catboost"] for row in folds],dtype=float);gains=np.asarray([row["catboost_improvement_oriented"] for row in folds],dtype=float)
    slope=float(np.polyfit(np.arange(1,6),cat_values,1)[0]);validation_gain=main["validation"]["catboost_minus_baseline_oriented"]
    stable=bool(validation_gain>0 and (gains>0).sum()>=3 and abs(slope)<=max(float(np.std(cat_values)),1e-12)*1.5)
    return {"primary_metric":metric,"higher_is_better":direction==1,"main":main,"train_validation_gap":{
        "baseline":direction*(main["train"]["baseline"]-main["validation"]["baseline"]),
        "catboost":direction*(main["train"]["catboost"]-main["validation"]["catboost"])},
        "walk_forward":{"folds":folds,"catboost_mean":float(cat_values.mean()),"catboost_std":float(cat_values.std()),
            "mean_improvement_oriented":float(gains.mean()),"improvement_std":float(gains.std()),"temporal_slope":slope,"folds_improved":int((gains>0).sum())},
        "stable_validation_and_walk_signal":stable}


def build_comparison(baseline_dir,catboost_dir):
    bm,bmetrics,bdetails=_read_experiment(baseline_dir);cm,cmetrics,cdetails=_read_experiment(catboost_dir)
    if bm["training_dataset_id"]!=cm["training_dataset_id"] or bm["training_dataset_checksum"]!=cm["training_dataset_checksum"]:raise ValueError("Experiments used different training datasets")
    tasks={task:_summarize_task(task,bmetrics,cmetrics) for task in PRIMARY};stable=sum(value["stable_validation_and_walk_signal"] for value in tasks.values());smoke=bool(bm.get("smoke") or cm.get("smoke"))
    recommendation=("smoke_only_no_signal_conclusion" if smoke else ("stable_predictive_signal_present_proceed_to_controlled_tuning" if stable>=2 else "insufficient_stable_predictive_signal_do_not_tune_or_deploy"))
    diagnostics={}
    for family,details in (("baseline",bdetails),("catboost",cdetails)):
        diagnostics[family]={task:{split:details["main"][task][split] for split in ("validation","test")} for task in PRIMARY}
    return {"created_at":datetime.now(timezone.utc).isoformat(),"smoke":smoke,"training_dataset_id":bm["training_dataset_id"],"training_dataset_checksum":bm["training_dataset_checksum"],
        "selection_policy":"Recommendation uses validation and walk-forward results only. Test metrics are reported untouched and are not used for model or threshold selection.",
        "tasks":tasks,"diagnostics_by_family_task_split":diagnostics,"stable_task_count":stable,"recommendation":recommendation,
        "cautions":["Train-validation gaps indicate overfitting when materially positive in the metric's favorable direction.",
            "Walk-forward standard deviation and temporal slope indicate instability or degradation.","This report is evaluation evidence, not deployment approval."]}


def write_comparison(report,output):
    output.mkdir(parents=True,exist_ok=True);jp=output/"comparison_report.json";mp=output/"comparison_report.md"
    jp.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n","utf-8")
    lines=["# Baseline versus CatBoost — Full `training_v1` Experiment","",f"- Recommendation: `{report['recommendation']}`",f"- Stable tasks: `{report['stable_task_count']} / 3`","",report["selection_policy"],""]
    for task,value in report["tasks"].items():
        lines += [f"## {task.title()}","",f"- Primary metric: `{value['primary_metric']}`",f"- Main train/validation/test: `{value['main']}`",
                  f"- Train-validation gaps: `{value['train_validation_gap']}`",f"- Walk-forward summary: `{value['walk_forward']}`",
                  f"- Stable validation/walk signal: `{value['stable_validation_and_walk_signal']}`",""]
    lines += ["Detailed class distributions, confusion matrices, calibration, score buckets, segment performance, regression predicted-versus-realized analysis, feature importance, and SHAP summaries are embedded in `comparison_report.json` and the source experiment artifacts.",""]
    mp.write_text("\n".join(lines),"utf-8")
    files=(jp,mp);checksums={path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in files};(output/"artifact_checksums.json").write_text(json.dumps(checksums,indent=2,sort_keys=True)+"\n","utf-8")
    return jp,mp


def main(argv=None):
    parser=argparse.ArgumentParser();parser.add_argument("--baseline-dir",type=Path,required=True);parser.add_argument("--catboost-dir",type=Path,required=True);parser.add_argument("--output-dir",type=Path,required=True);args=parser.parse_args(argv)
    report=build_comparison(args.baseline_dir.resolve(),args.catboost_dir.resolve());paths=write_comparison(report,args.output_dir.resolve());print(json.dumps({"recommendation":report["recommendation"],"reports":[str(path) for path in paths]},indent=2));return 0


if __name__=="__main__":raise SystemExit(main())
