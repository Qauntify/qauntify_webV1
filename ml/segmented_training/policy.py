"""Validation-only post-training diagnostics, ablations, causal ranking, and policy locking."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss, roc_auc_score

from ml.thresholding.metrics import policy_metrics, safeguards
from ml.training.runner import _sha256, _write_json

CHECKS=("positive_mean_net_r","positive_total_net_r","minimum_coverage","positive_fold_count",
        "minimum_candidate_count_per_fold","positive_after_estimated_costs","fold_concentration_passed",
        "year_concentration_passed","cost_sensitivity_passed")


def causal_score_percentile(frame, minimum_history=100):
    result=pd.Series(np.nan,index=frame.index,dtype=float)
    for _,group in frame.groupby("fold",sort=True):
        ordered=group.sort_values(["candidate_timestamp","candidate_id"],kind="mergesort")
        values=ordered.calibrated_probability.to_numpy(dtype=float); coordinates=np.unique(values); tree=np.zeros(len(coordinates)+1,dtype=np.int64)
        def query(position):
            total=0
            while position>0: total+=int(tree[position]); position-=position&-position
            return total
        def update(position):
            while position<len(tree): tree[position]+=1; position+=position&-position
        for seen,(index,value) in enumerate(zip(ordered.index,values)):
            position=int(np.searchsorted(coordinates,value,side="right"))
            if seen>=minimum_history: result.loc[index]=float(query(position)/seen)
            update(int(np.searchsorted(coordinates,value,side="left"))+1)
    return result


def _load_predictions(root,segment):
    files=sorted((Path(root)/"predictions"/segment).glob("fold_*.parquet"))
    if len(files)!=5: raise ValueError(f"Expected five prediction folds for {segment}; found {len(files)}")
    frame=pd.concat([pd.read_parquet(path) for path in files],ignore_index=True)
    if set(frame.fold)!={1,2,3,4,5} or frame[["candidate_id","fold"]].duplicated().any(): raise ValueError("Invalid outer OOF coverage")
    frame["candidate_timestamp"]=pd.to_datetime(frame.candidate_timestamp,utc=True); frame["causal_score_percentile"]=causal_score_percentile(frame)
    return frame


def _economic_checks(frame,mask,config):
    guards=config.safeguards; cost=float(guards["primary_cost_r"]); metrics=policy_metrics(frame,mask,cost_r=cost)
    checks,passed=safeguards(metrics,minimum_coverage=float(guards["minimum_coverage"]),
        minimum_positive_folds=int(guards["minimum_positive_folds"]),minimum_count_per_fold=int(guards["minimum_candidates_per_fold"]))
    counts=np.asarray([row["candidate_count"] for row in metrics["folds"].values()]); total=max(int(counts.sum()),1); fold_share=float(counts.max()/total)
    selected=frame[mask].copy(); selected["after_cost_r"]=selected.target_net_realized_r-cost; selected["year"]=selected.candidate_timestamp.dt.year
    yearly=selected.groupby("year").after_cost_r.sum(); positive=yearly[yearly>0]; year_share=float(positive.max()/positive.sum()) if len(positive) and positive.sum()>0 else 1.0
    sensitivity={}; sensitivity_passed=True
    for value in guards["sensitivity_costs_r"]:
        item=policy_metrics(frame,mask,cost_r=float(value)); sensitivity[str(value)]=item
        sensitivity_passed &= item["mean_r"]>0 and item["total_r"]>0 and item["positive_folds"]>=int(guards["minimum_positive_folds"])
    extra={"maximum_fold_candidate_share":fold_share,"maximum_year_profit_share":year_share,
        "fold_concentration_passed":fold_share<=float(guards["maximum_fold_candidate_share"]),
        "year_concentration_passed":year_share<=float(guards["maximum_year_profit_share"]),
        "cost_sensitivity_passed":bool(sensitivity_passed)}
    eligible=bool(passed and all(extra[key] for key in ("fold_concentration_passed","year_concentration_passed","cost_sensitivity_passed")))
    return metrics,checks,extra,sensitivity,eligible


def _mask(frame,gate,value):
    if gate=="binary_only": return frame.calibrated_probability>=value
    if gate=="regression_only": return frame.predicted_regression_r>0
    if gate=="binary_and_regression": return (frame.calibrated_probability>=value)&(frame.predicted_regression_r>0)
    if gate=="causal_rank_only": return frame.causal_score_percentile>=value
    if gate=="causal_rank_and_regression": return (frame.causal_score_percentile>=value)&(frame.predicted_regression_r>0)
    raise ValueError(gate)


def _fold_diagnostics(frame):
    rows=[]
    for fold,group in frame.groupby("fold",sort=True):
        target=group.target_binary_success.astype(int); regression=group.predicted_regression_r.astype(float)
        rows.append({"fold":int(fold),"rows":len(group),"timestamp_min":group.candidate_timestamp.min().isoformat(),"timestamp_max":group.candidate_timestamp.max().isoformat(),
            "target_rate":float(target.mean()),"binary_auc":float(roc_auc_score(target,group.calibrated_probability)) if target.nunique()==2 else None,
            "binary_brier":float(brier_score_loss(target,group.calibrated_probability)),
            "regression_spearman":float(regression.corr(group.target_net_realized_r,method="spearman")) if regression.nunique()>1 else None,
            "probability_quantiles":{str(q):float(v) for q,v in group.calibrated_probability.quantile([0,.05,.25,.5,.75,.95,1]).items()},
            "regression_quantiles":{str(q):float(v) for q,v in regression.quantile([0,.05,.25,.5,.75,.95,1]).items()},
            "ablation_counts_at_050":{"all":len(group),"binary_only":int((group.calibrated_probability>=.5).sum()),
                "regression_only":int((regression>0).sum()),"combined":int(((group.calibrated_probability>=.5)&(regression>0)).sum())}})
    return rows


def select_segmented_policy(config,*,experiment_dir):
    root=Path(experiment_dir).resolve(); out=root/"post_training_analysis"; out.mkdir(parents=True,exist_ok=True)
    if (out/"test_evaluation_state.json").exists(): raise ValueError("Test evaluation already started; selection is frozen")
    all_rows=[]; diagnostics={}; frames={}; masks={}
    absolute=[round(value,3) for value in np.arange(.40,.6001,.005)]; ranks=[.80,.85,.90,.925,.95]
    for segment in config.segments:
        name=segment["id"]; frame=_load_predictions(root,name); frames[name]=frame; diagnostics[name]=_fold_diagnostics(frame)
        for gate,values in (("binary_only",absolute),("regression_only",[0.0]),("binary_and_regression",absolute),("causal_rank_only",ranks),("causal_rank_and_regression",ranks)):
            for value in values:
                mask=_mask(frame,gate,value); metrics,checks,extra,sensitivity,eligible=_economic_checks(frame,mask,config); policy_id=f"{name}__{gate}__{value:.3f}"
                row={"policy_id":policy_id,"segment":name,"gate":gate,"value":value,**{k:v for k,v in metrics.items() if k!="folds"},**checks,**extra,
                    "eligible":eligible,"failed_safeguards":[key for key in CHECKS if not {**checks,**extra}.get(key,False)],"folds":metrics["folds"],"cost_sensitivity":sensitivity}
                all_rows.append(row); masks[policy_id]=mask
    all_rows.sort(key=lambda row:(-int(row["eligible"]),-row["positive_folds"],-row["minimum_fold_candidate_count"],-row["mean_r"],row["policy_id"]))
    winner=next((row for row in all_rows if row["eligible"]),None)
    _write_json(out/"fold_diagnostics.json",diagnostics); _write_json(out/"policy_candidates.json",all_rows)
    best_rejected={name:next(row for row in all_rows if row["segment"]==name) for name in frames}
    zero_trade={}
    for name,row in best_rejected.items():
        frame=frames[name]; mask=masks[row["policy_id"]]; zero_trade[name]={"reference_policy":row["policy_id"],"zero_trade_folds":[],"gate_counts":{}}
        for fold in range(1,6):
            group=frame[frame.fold==fold]; counts={"all":len(group),"binary_only":int((group.calibrated_probability>=row["value"]).sum()) if "binary" in row["gate"] else None,
                "regression_only":int((group.predicted_regression_r>0).sum()),"final":int(mask.loc[group.index].sum())}
            zero_trade[name]["gate_counts"][str(fold)]=counts
            if counts["final"]==0: zero_trade[name]["zero_trade_folds"].append(fold)
    _write_json(out/"zero_trade_investigation.json",zero_trade)
    locked=None
    if winner:
        locked={key:winner[key] for key in ("policy_id","segment","gate","value","coverage","candidate_count","mean_r","total_r","profit_factor","maximum_drawdown_r","positive_folds","folds","cost_sensitivity")}
        locked.update({"version":"segmented_policy_v1","status":"locked","created_at":datetime.now(timezone.utc).isoformat(),"selection_data":"outer OOF validation only; untouched test excluded",
            "minimum_history_for_causal_rank":100,"test_policy":"evaluate exactly once only after lock","deployment_status":"not_approved"})
        _write_json(out/"locked_policy.json",locked)
    report={"version":"segmented_policy_v1","status":"locked" if locked else "rejected","candidate_policies":len(all_rows),"eligible_policies":sum(row["eligible"] for row in all_rows),
        "winner":winner,"best_rejected":best_rejected,"test_rows_used":0,"deployment_status":"not_approved"}; _write_json(out/"selection_report.json",report)
    lines=["# Segmented post-training policy analysis","",f"- Status: `{report['status']}`",f"- Candidate policies: `{len(all_rows)}`",f"- Eligible policies: `{report['eligible_policies']}`","- Test rows used: `0`",""]
    if winner: lines += [f"- Locked policy: `{winner['policy_id']}`",f"- Coverage: `{winner['coverage']}`",f"- Mean/total R: `{winner['mean_r']}` / `{winner['total_r']}`",""]
    else: lines += ["No policy passed every fixed safeguard. Untouched-test evaluation is forbidden.",""]
    (out/"selection_report.md").write_text("\n".join(lines),"utf-8")
    manifest={"version":"segmented_policy_v1","status":report["status"],"test_rows_used":0,"locked_policy_count":int(locked is not None),"candidate_policy_count":len(all_rows)}; _write_json(out/"manifest.json",manifest)
    files=sorted(path for path in out.rglob("*") if path.is_file() and path.name!="artifact_checksums.json"); _write_json(out/"artifact_checksums.json",{str(path.relative_to(out)).replace("\\","/"):_sha256(path) for path in files})
    return manifest
