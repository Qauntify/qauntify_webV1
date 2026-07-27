"""Segment filtering and past-only nested calibration folds."""
from __future__ import annotations
import pandas as pd


def filter_segment(frame, segment):
    return frame[(frame.strategy_name.astype(str)==segment["strategy_name"]) &
                 (frame.timeframe.astype(str)==segment["timeframe"])].sort_values(["candidate_timestamp","candidate_id"],kind="mergesort").reset_index(drop=True)


def build_inner_calibration_folds(outer_train, policy):
    ordered=outer_train.sort_values(["candidate_timestamp","candidate_id"],kind="mergesort").reset_index(drop=True)
    timestamp=pd.to_datetime(ordered.candidate_timestamp,utc=True); embargo=pd.Timedelta(days=int(policy["embargo_days"])); folds=[]
    for index in range(int(policy["folds"])):
        start=float(policy["initial_train_fraction"])+index*float(policy["validation_fraction"]); end=start+float(policy["validation_fraction"])
        start_pos=min(max(int(len(ordered)*start),1),len(ordered)-1); end_pos=min(max(int(len(ordered)*end),start_pos+1),len(ordered))
        validation_start=timestamp.iloc[start_pos]; validation_end=timestamp.iloc[end_pos] if end_pos<len(ordered) else timestamp.max()+pd.Timedelta(microseconds=1)
        train=ordered[timestamp < validation_start-embargo].copy(); validation=ordered[(timestamp>=validation_start)&(timestamp<validation_end)].copy()
        if train.empty or validation.empty or train.candidate_timestamp.max()>=validation.candidate_timestamp.min(): raise ValueError("Inner temporal fold is empty or leaks")
        folds.append({"fold":index+1,"train":train,"validation":validation,"validation_start":validation_start})
    validation_ids=[set(item["validation"].candidate_id) for item in folds]
    if any(validation_ids[i]&validation_ids[j] for i in range(len(folds)) for j in range(i+1,len(folds))): raise ValueError("Inner validation folds overlap")
    return folds


def assert_outer_isolation(inner_folds, outer_validation):
    outer_ids=set(outer_validation.candidate_id); used=set()
    for item in inner_folds: used.update(item["train"].candidate_id); used.update(item["validation"].candidate_id)
    if used & outer_ids: raise ValueError("Outer validation entered calibration fitting")
    if max(max(item["train"].candidate_timestamp),max(item["validation"].candidate_timestamp)) >= min(outer_validation.candidate_timestamp):
        raise ValueError("Future timestamp entered calibration fitting")
    return True
