"""Past-only calibrator fitting and selection."""
import numpy as np
from sklearn.metrics import brier_score_loss, log_loss
from ml.thresholding.calibration import _fit, _new_calibrator, apply_calibrator


def fit_temporal_calibrator(frame, policy):
    target=frame.target_binary_success.to_numpy(dtype=int); rows=[]; models={}
    methods=["sigmoid"]
    counts=np.bincount(target,minlength=2)
    if len(frame)>=int(policy["isotonic_minimum_rows"]) and counts.min()>=int(policy["minimum_class_rows"]): methods.append("isotonic")
    for method in methods:
        model=_fit(_new_calibrator(method),method,frame.raw_probability,target); probability=np.clip(apply_calibrator(model,method,frame.raw_probability),1e-8,1-1e-8)
        rows.append({"method":method,"brier_score":float(brier_score_loss(target,probability)),"log_loss":float(log_loss(target,probability,labels=[0,1]))}); models[method]=model
    rows.sort(key=lambda row:(row["brier_score"],row["log_loss"],row["method"])); selected=rows[0]["method"]
    return selected,models[selected],{"selected_method":selected,"candidates":rows,"rows":len(frame),"policy":"past-only nested OOF"}
