"""Evaluation artifacts derived without changing models or thresholds."""
from __future__ import annotations

import math
import warnings
import numpy as np
import pandas as pd

from ml.training.evaluation import evaluate


def build_prediction_frame(task, source, prediction, probabilities, classes, split):
    target_name={"binary":"target_binary_success","multiclass":"target_outcome_class","regression":"target_net_realized_r"}[task]
    output=source[["candidate_id","candidate_timestamp","strategy_name","timeframe","direction","year"]].copy()
    output["split"]=split; output["target"]=source[target_name].to_numpy(); output["prediction"]=prediction
    if probabilities is not None:
        for index,label in enumerate(classes): output[f"probability_{label}"]=probabilities[:,index]
        output["score"] = probabilities[:,list(classes).index(1)] if task=="binary" else probabilities.max(axis=1)
    else: output["score"]=np.asarray(prediction,dtype="float64")
    ranked=output.score.rank(method="first")
    output["score_bucket"]=pd.qcut(ranked,q=min(10,len(output)),labels=False,duplicates="drop").astype("int16")+1
    return output


def _probabilities(frame, classes):
    if classes is None: return None
    return frame[[f"probability_{label}" for label in classes]].to_numpy()


def _group_metrics(task, frame, classes):
    if frame.empty: return {}
    target=frame.target.to_numpy(); prediction=frame.prediction.to_numpy(); probabilities=_probabilities(frame,classes)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        result=evaluate(task,target,prediction,probabilities,classes)
    result.update({"rows":len(frame),"target_mean":float(pd.to_numeric(frame.target,errors="coerce").mean()) if task!="multiclass" else None,
                   "prediction_mean":float(pd.to_numeric(frame.prediction,errors="coerce").mean()) if task!="multiclass" else None,
                   "score_mean":float(frame.score.mean())})
    return result


def calibration_table(task, frame, bins=10):
    work=frame.copy()
    if task in {"binary","multiclass"}:
        work["calibration_bin"]=pd.cut(work.score,bins=np.linspace(0,1,bins+1),include_lowest=True,labels=False)
        work["observed"]=(work.target==work.prediction).astype(float) if task=="multiclass" else pd.to_numeric(work.target)
    else:
        work["calibration_bin"]=pd.qcut(work.score.rank(method="first"),q=min(bins,len(work)),labels=False,duplicates="drop")
        work["observed"]=pd.to_numeric(work.target)
    return work.groupby("calibration_bin",dropna=False).agg(rows=("candidate_id","size"),mean_score=("score","mean"),mean_observed=("observed","mean")).reset_index()


def analyze_predictions(task, frame, classes, bins=10):
    from sklearn.metrics import confusion_matrix
    report={"overall":_group_metrics(task,frame,classes),"target_distribution":{str(k):int(v) for k,v in frame.target.value_counts(dropna=False).items()},"segments":{}}
    for dimension in ("strategy_name","timeframe","direction","year","score_bucket"):
        report["segments"][dimension]={str(value):_group_metrics(task,group,classes) for value,group in frame.groupby(dimension,dropna=False)}
    if task!="regression":
        labels=list(classes); matrix=confusion_matrix(frame.target,frame.prediction,labels=labels)
        report["confusion_matrix"]={"labels":[str(value) for value in labels],"matrix":matrix.astype(int).tolist()}
    else:
        actual=pd.to_numeric(frame.target).to_numpy(dtype=float); predicted=pd.to_numeric(frame.prediction).to_numpy(dtype=float)
        correlation=float(np.corrcoef(actual,predicted)[0,1]) if np.std(predicted)>0 else None
        slope,intercept=(np.polyfit(predicted,actual,1) if len(predicted)>1 and np.ptp(predicted)>1e-12 else (None,None))
        report["predicted_vs_realized_r"]={"correlation":correlation,"slope":float(slope) if slope is not None else None,
            "intercept":float(intercept) if intercept is not None else None,"mean_error":float(np.mean(predicted-actual)),
            "error_std":float(np.std(predicted-actual))}
    report["calibration"]=calibration_table(task,frame,bins).to_dict("records")
    return report


def feature_diagnostics(model, task, validation, features, categorical, shap_rows):
    importance=np.asarray(model.get_feature_importance(),dtype=float).reshape(-1)
    result={"feature_importance":[{"feature":name,"importance":float(value)} for name,value in sorted(zip(features,importance),key=lambda item:item[1],reverse=True)]}
    if shap_rows<=0: return result
    from catboost import Pool
    sample=validation.head(shap_rows); target={"binary":"target_binary_success","multiclass":"target_outcome_class","regression":"target_net_realized_r"}[task]
    target_dtype="float64" if task=="regression" else ("int64" if task=="binary" else "str")
    pool=Pool(sample[list(features)],np.asarray(sample[target],dtype=target_dtype),cat_features=list(categorical),feature_names=list(features))
    values=np.asarray(model.get_feature_importance(pool,type="ShapValues"))
    contributions=np.abs(values[..., :-1]); axes=tuple(range(contributions.ndim-1)); means=contributions.mean(axis=axes)
    result["shap_summary"]={"sample_rows":len(sample),"mean_absolute_shap":[{"feature":name,"mean_abs_shap":float(value)} for name,value in sorted(zip(features,means),key=lambda item:item[1],reverse=True)]}
    return result
