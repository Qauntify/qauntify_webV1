"""Production-only ML feature, artifact, and inference interfaces.

No model is connected to live signal enforcement by this package.
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
