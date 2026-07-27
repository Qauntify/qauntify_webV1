import pandas as pd
import pytest

from ml.thresholding.diagnostics import _distribution, _fold_report


def _frame():
    rows = []
    for fold in range(1, 6):
        for index in range(4):
            rows.append({"candidate_id": f"{fold}-{index}", "fold": fold,
                         "candidate_timestamp": pd.Timestamp("2024-01-01", tz="UTC") + pd.Timedelta(days=fold * 10 + index),
                         "target_binary_success": index % 2, "target_net_realized_r": .2 if index % 2 else -.1,
                         "raw_probability": .4 + fold * .01 + index * .02,
                         "calibrated_probability": .42 + fold * .01 + index * .02})
    return pd.DataFrame(rows)


def test_distribution_is_deterministic():
    result = _distribution(pd.Series([.1, .2, .3]))
    assert result["count"] == 3
    assert result["mean"] == pytest.approx(.2)
    assert result["minimum"] == .1
    assert result["maximum"] == .3


def test_fold_report_proves_cross_fit_isolation():
    result = _fold_report(_frame(), 3, (.5,), .02)
    assert result["cross_fit_proof"] == {"fit_folds": [1, 2, 4, 5], "apply_fold": 3,
        "fit_rows": 16, "apply_rows": 4, "overlap_rows": 0}
    assert result["rows"] == 4
    assert result["thresholds"][0]["threshold"] == .5
