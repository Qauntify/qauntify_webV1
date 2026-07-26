import pandas as pd
import pytest

from ml.segmented_training.calibration import fit_temporal_calibrator
from ml.segmented_training.config import load_segmented_config
from ml.segmented_training.data import assert_outer_isolation, build_inner_calibration_folds, filter_segment
from ml.segmented_training.runner import _policy_table


def _rows(count=300):
    return pd.DataFrame({
        "candidate_id":[f"c-{index:04d}" for index in range(count)],
        "candidate_timestamp":pd.date_range("2020-01-01",periods=count,freq="D",tz="UTC"),
        "strategy_name":["ict_fvg" if index%2 else "sr_zone" for index in range(count)],
        "timeframe":["M5" if index%2 else "M15" for index in range(count)],
        "target_binary_success":[index%2 for index in range(count)],
        "target_net_realized_r":[.5 if index%3 else -.4 for index in range(count)],
    })


def test_config_locks_temporal_and_cost_contract():
    config=load_segmented_config("ml/configs/training_v2_segmented_temporal.yaml")
    assert len(config.segments)==2
    assert config.inner["folds"]==3
    assert config.safeguards["minimum_candidates_per_fold"]==100
    assert config.safeguards["sensitivity_costs_r"]==[.03,.05]


def test_segment_filter_is_exact():
    selected=filter_segment(_rows(20),{"strategy_name":"ict_fvg","timeframe":"M5"})
    assert len(selected)==10
    assert set(selected.strategy_name)=={"ict_fvg"}
    assert set(selected.timeframe)=={"M5"}


def test_inner_folds_are_past_only_and_disjoint():
    frame=_rows(300)
    policy={"folds":3,"initial_train_fraction":.55,"validation_fraction":.10,"embargo_days":14}
    folds=build_inner_calibration_folds(frame,policy)
    assert len(folds)==3
    for item in folds:
        assert item["train"].candidate_timestamp.max()<item["validation"].candidate_timestamp.min()
    assert assert_outer_isolation(folds,_rows(20).assign(candidate_id=lambda value:"outer-"+value.candidate_id,
        candidate_timestamp=pd.date_range("2022-01-01",periods=20,freq="D",tz="UTC")))


def test_outer_overlap_is_rejected():
    frame=_rows(300); folds=build_inner_calibration_folds(frame,{"folds":3,"initial_train_fraction":.55,"validation_fraction":.10,"embargo_days":14})
    with pytest.raises(ValueError,match="Outer validation entered"):
        assert_outer_isolation(folds,folds[0]["validation"])


def test_isotonic_guard_falls_back_to_sigmoid():
    frame=pd.DataFrame({"raw_probability":[.3,.4,.6,.7],"target_binary_success":[0,0,1,1]})
    method,_,report=fit_temporal_calibrator(frame,{"isotonic_minimum_rows":1000,"minimum_class_rows":50})
    assert method=="sigmoid"
    assert [item["method"] for item in report["candidates"]]==["sigmoid"]


def test_policy_selection_is_deterministic_and_does_not_lower_volume_guard():
    config=load_segmented_config("ml/configs/training_v2_segmented_temporal.yaml")
    rows=[]
    for fold in range(1,6):
        for index in range(50):
            rows.append({"candidate_id":f"{fold}-{index}","fold":fold,
                "candidate_timestamp":pd.Timestamp("2020-01-01",tz="UTC")+pd.Timedelta(days=fold*100+index),
                "calibrated_probability":.55,"predicted_regression_r":.2,"target_net_realized_r":.3})
    frame=pd.DataFrame(rows)
    first,winner,_=_policy_table(frame,config); second,_,_=_policy_table(frame,config)
    assert first==second
    assert winner is None
    assert not first[0]["minimum_candidate_count_per_fold"]
