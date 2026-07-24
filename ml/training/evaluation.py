"""Task-specific evaluation with stable JSON-compatible metrics."""
from __future__ import annotations

import math
import numpy as np


def evaluate(task, y_true, prediction, probabilities=None, classes=None):
    from sklearn.metrics import (accuracy_score, balanced_accuracy_score, f1_score, log_loss,
        mean_absolute_error, mean_squared_error, precision_score, r2_score, recall_score, roc_auc_score)
    if task == "regression":
        import pandas as pd
        spearman = None if len(np.unique(prediction)) < 2 or len(np.unique(y_true)) < 2 else pd.Series(y_true).corr(pd.Series(prediction), method="spearman")
        result = {"mae": mean_absolute_error(y_true,prediction), "rmse": math.sqrt(mean_squared_error(y_true,prediction)),
                  "r2": r2_score(y_true,prediction), "spearman": float(spearman) if spearman is not None and math.isfinite(float(spearman)) else None}
    elif task == "binary":
        result = {"accuracy":accuracy_score(y_true,prediction), "balanced_accuracy":balanced_accuracy_score(y_true,prediction),
                  "precision":precision_score(y_true,prediction,zero_division=0), "recall":recall_score(y_true,prediction,zero_division=0),
                  "f1":f1_score(y_true,prediction,zero_division=0)}
        if probabilities is not None and len(np.unique(y_true)) == 2:
            positive_index = list(classes).index(1); result["roc_auc"] = roc_auc_score(y_true, probabilities[:,positive_index]); result["log_loss"] = log_loss(y_true,probabilities,labels=list(classes))
    else:
        result = {"accuracy":accuracy_score(y_true,prediction), "balanced_accuracy":balanced_accuracy_score(y_true,prediction),
                  "macro_f1":f1_score(y_true,prediction,average="macro",zero_division=0)}
        if probabilities is not None: result["log_loss"] = log_loss(y_true,probabilities,labels=list(classes))
    return {key: (float(value) if value is not None else None) for key,value in result.items()}
