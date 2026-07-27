import numpy as np
import pandas as pd

from ml.segmented_training.config import load_segmented_config
from ml.segmented_training.policy import _economic_checks, _mask, causal_score_percentile


def _frame(rows_per_fold=150):
    rows=[]
    for fold in range(1,6):
        for index in range(rows_per_fold):
            rows.append({"candidate_id":f"{fold}-{index}","fold":fold,
                "candidate_timestamp":pd.Timestamp("2015-01-01",tz="UTC")+pd.Timedelta(days=(fold-1)*400+index),
                "calibrated_probability":.4+.001*index,"predicted_regression_r":.2,
                "target_binary_success":index%2,"target_net_realized_r":.20})
    return pd.DataFrame(rows)


def test_causal_rank_does_not_change_when_future_rows_are_appended():
    original=_frame(120); before=causal_score_percentile(original)
    future=pd.DataFrame([{"candidate_id":"1-future","fold":1,"candidate_timestamp":pd.Timestamp("2030-01-01",tz="UTC"),
        "calibrated_probability":.99,"predicted_regression_r":1.,"target_binary_success":1,"target_net_realized_r":1.}])
    after=causal_score_percentile(pd.concat([original,future],ignore_index=True)).iloc[:len(original)]
    np.testing.assert_allclose(before.to_numpy(),after.to_numpy(),equal_nan=True)


def test_filter_ablation_masks_are_distinct():
    frame=_frame(120); frame["causal_score_percentile"]=causal_score_percentile(frame)
    assert _mask(frame,"binary_only",.5).sum()!=_mask(frame,"regression_only",0).sum()
    assert _mask(frame,"binary_and_regression",.5).sum()==_mask(frame,"binary_only",.5).sum()
    assert _mask(frame,"causal_rank_only",.9).sum()>0


def test_all_fixed_safeguards_are_required_for_eligibility():
    config=load_segmented_config("ml/configs/training_v2_segmented_temporal.yaml"); frame=_frame(150); mask=pd.Series(True,index=frame.index)
    _,checks,extra,_,eligible=_economic_checks(frame,mask,config)
    assert eligible
    assert all(checks.values())
    assert extra["fold_concentration_passed"] and extra["year_concentration_passed"] and extra["cost_sensitivity_passed"]


def test_minimum_sample_guard_rejects_sparse_policy():
    config=load_segmented_config("ml/configs/training_v2_segmented_temporal.yaml"); frame=_frame(150); mask=frame.groupby("fold").cumcount()<10
    _,checks,_,_,eligible=_economic_checks(frame,mask,config)
    assert not eligible
    assert not checks["minimum_candidate_count_per_fold"]
