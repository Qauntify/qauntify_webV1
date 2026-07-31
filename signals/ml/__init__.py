"""ML feature, artifact, and inference interfaces — NOT WIRED INTO THE ENGINE.

    Nothing in the live signal path imports this package.

`signals/run.py` and `signals/xau_scan.py` produce every delivered signal from
the deterministic detectors in `signals/strategies/` plus the SEA-LION
confirmation gate. No model in `model/` is loaded, no feature here is computed,
and no prediction influences what a user receives. `tests/core/test_ml_not_wired.py`
asserts that and will fail the moment it stops being true.

This is research scaffolding kept in-tree so training and serving can share one
feature definition. Treat it as such: the progress report in
`docs/ml-training-progress-report.md` is explicit that leakage-safety of the
training data has not been verified end to end, so nothing here is ready to
gate real trades.

To connect it, put it behind a sampling flag and shadow-record its verdict the
way the LLM confirmation gate is measured (see
`docs/superpowers/specs/2026-07-26-ai-gate-ab-design.md`) — measure first,
enforce second.
"""

from signals.ml.expected_r import OUTCOME_LABELS, calculate_expected_r
from signals.ml.features import CandidateFeatureInput, build_candidate_features
from signals.ml.predictor import PredictionResult, score_candidate

__all__ = [
    "CandidateFeatureInput",
    "OUTCOME_LABELS",
    "PredictionResult",
    "build_candidate_features",
    "calculate_expected_r",
    "score_candidate",
]
