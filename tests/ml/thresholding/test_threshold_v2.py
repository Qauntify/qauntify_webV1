from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from ml.thresholding.calibration import cross_fit_calibration
from ml.thresholding.config import ThresholdConfigurationError, load_threshold_config, require_assumptions
from ml.thresholding.metrics import policy_metrics, safeguards
from ml.thresholding.test_evaluation import evaluate_untouched_test_once


def _frame():
    rows = []
    for fold in range(1, 6):
        for index in range(40):
            target = int(index >= 20)
            rows.append({"candidate_id": f"{fold}-{index}", "candidate_timestamp": pd.Timestamp("2020-01-01", tz="UTC") + pd.Timedelta(days=fold, minutes=index),
                         "fold": fold, "raw_probability": 0.42 + index / 200, "target_binary_success": target,
                         "target_net_realized_r": 1.0 if target else -0.4})
    return pd.DataFrame(rows)


def test_config_reports_required_missing_assumptions():
    config = load_threshold_config(Path("ml/configs/threshold_v2.yaml"))
    assert config.missing_assumptions == ()
    assert config.minimum_count_per_fold == 100 and config.trading_cost_r == 0.02
    assert config.cost_sensitivity_r == (0.03, 0.05)
    missing = replace(config, minimum_count_per_fold=None, trading_cost_r=None)
    with pytest.raises(ThresholdConfigurationError, match="Missing required assumptions"):
        require_assumptions(missing)
    ready = replace(config, minimum_count_per_fold=5)
    assert ready.missing_assumptions == ()


def test_cross_fitted_calibration_covers_all_folds_without_test_rows():
    frame = _frame()
    calibrated, report, model = cross_fit_calibration(frame, ("sigmoid", "isotonic"))
    assert calibrated.calibrated_probability.notna().all()
    assert calibrated.calibrated_probability.between(0, 1).all()
    assert report["selected_method"] in {"sigmoid", "isotonic"}
    assert "test excluded" in report["data_policy"]
    assert model is not None


def test_economic_safeguards_require_cost_positive_fold_consistency_and_count():
    frame = _frame()
    accepted = frame.raw_probability >= 0.52
    metrics = policy_metrics(frame, accepted, cost_r=0.02)
    checks, eligible = safeguards(metrics, minimum_coverage=0.05, minimum_positive_folds=4, minimum_count_per_fold=5)
    assert eligible and all(checks.values())
    _, rejected = safeguards(metrics, minimum_coverage=0.90, minimum_positive_folds=5, minimum_count_per_fold=100)
    assert not rejected


def test_exactly_once_guard_fires_before_models_or_test_data_are_loaded(tmp_path):
    (tmp_path / "locked_policy.json").write_text("{}", "utf-8")
    (tmp_path / "test_evaluation_state.json").write_text("{}", "utf-8")
    config = SimpleNamespace(missing_assumptions=(), minimum_count_per_fold=5, trading_cost_r=0.02, output_root=tmp_path)
    with pytest.raises(FileExistsError, match="already started"):
        evaluate_untouched_test_once(config, output_dir=tmp_path, confirmed=True)


def test_test_evaluation_requires_explicit_confirmation(tmp_path):
    config = SimpleNamespace(missing_assumptions=(), minimum_count_per_fold=5, trading_cost_r=0.02, output_root=tmp_path)
    with pytest.raises(ValueError, match="confirm-untouched-test"):
        evaluate_untouched_test_once(config, output_dir=tmp_path, confirmed=False)


def test_colab_notebook_keeps_test_evaluation_explicitly_locked():
    notebook = json.loads(Path("ml/notebooks/threshold_v2_colab.ipynb").read_text("utf-8"))
    source = "\n".join("".join(cell.get("source", [])) for cell in notebook["cells"])
    assert "ml.thresholding.cli" in source
    assert "RUN_UNTOUCHED_TEST = False" in source
    assert "--confirm-untouched-test" in source
    assert "MINIMUM_COUNT_PER_FOLD = 100" in source and "TRADING_COST_R = 0.02" in source
    assert "CatBoostClassifier(" not in source and "ml.training.cli" not in source
