"""Cross-fitted probability calibration using OOF predictions only."""
from __future__ import annotations

import numpy as np
import pandas as pd


def _new_calibrator(method):
    if method == "sigmoid":
        from sklearn.linear_model import LogisticRegression
        return LogisticRegression(C=1e6, solver="lbfgs", random_state=42)
    if method == "isotonic":
        from sklearn.isotonic import IsotonicRegression
        return IsotonicRegression(out_of_bounds="clip")
    raise ValueError(f"Unknown calibration method: {method}")


def _fit(model, method, score, target):
    X = np.asarray(score, dtype=float)
    y = np.asarray(target, dtype=int)
    return model.fit(X.reshape(-1, 1), y) if method == "sigmoid" else model.fit(X, y)


def apply_calibrator(model, method, score):
    values = np.asarray(score, dtype=float)
    if method == "sigmoid":
        return model.predict_proba(values.reshape(-1, 1))[:, 1]
    return np.asarray(model.predict(values), dtype=float)


def cross_fit_calibration(frame: pd.DataFrame, methods):
    from sklearn.metrics import brier_score_loss, log_loss

    candidates = []
    outputs = {}
    models = {}
    for method in methods:
        calibrated = np.full(len(frame), np.nan, dtype=float)
        for fold in range(1, 6):
            train = frame.fold != fold
            validation = frame.fold == fold
            model = _fit(_new_calibrator(method), method, frame.loc[train, "raw_probability"], frame.loc[train, "target_binary_success"])
            calibrated[validation.to_numpy()] = apply_calibrator(model, method, frame.loc[validation, "raw_probability"])
        if np.isnan(calibrated).any():
            raise ValueError("Calibration did not cover every OOF row")
        target = frame.target_binary_success.to_numpy(dtype=int)
        candidates.append({"method": method, "brier_score": float(brier_score_loss(target, calibrated)),
                           "log_loss": float(log_loss(target, np.clip(calibrated, 1e-8, 1 - 1e-8)))})
        outputs[method] = calibrated
        models[method] = _fit(_new_calibrator(method), method, frame.raw_probability, frame.target_binary_success)
    candidates.sort(key=lambda row: (row["brier_score"], row["log_loss"], row["method"]))
    selected = candidates[0]["method"]
    result = frame.copy()
    result["calibrated_probability"] = outputs[selected]
    return result, {"selected_method": selected, "candidates": candidates,
                    "data_policy": "cross-fitted OOF validation predictions only; untouched test excluded"}, models[selected]

