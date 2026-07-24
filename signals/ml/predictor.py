"""Format-neutral scoring interface for approved, already loaded models."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Mapping, Protocol, Sequence

from signals.ml.exceptions import InferenceError, MLError
from signals.ml.expected_r import OUTCOME_LABELS, calculate_expected_r
from signals.ml.feature_schema import FeatureSchema, FeatureValue, validate_feature_schema


class ProbabilityModel(Protocol):
    """Small interface implemented by calibrated classification models."""

    def predict_proba(self, rows: Sequence[Sequence[FeatureValue]]) -> object: ...


@dataclass(frozen=True)
class PredictionResult:
    model_name: str
    model_version: str
    feature_schema_version: str
    probabilities: dict[str, float]
    expected_r: float
    accepted: bool
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


def _first_probability_row(raw: object) -> tuple[float, ...]:
    try:
        row = raw[0]  # type: ignore[index]
        return tuple(float(value) for value in row)
    except (IndexError, TypeError, ValueError) as exc:
        raise InferenceError("Model returned an invalid probability matrix") from exc


def score_candidate(
    *,
    model: ProbabilityModel,
    features: Mapping[str, FeatureValue],
    schema: FeatureSchema,
    model_name: str,
    model_version: str,
    minimum_expected_r: float,
    estimated_cost_r: float = 0.0,
) -> PredictionResult:
    """Validate one feature row, score it, and apply an expected-R threshold."""
    try:
        validate_feature_schema(features, schema)
        raw = model.predict_proba([tuple(features.values())])
        values = _first_probability_row(raw)
        if len(values) != len(OUTCOME_LABELS):
            raise InferenceError(
                f"Model returned {len(values)} classes; expected {len(OUTCOME_LABELS)}"
            )
        probabilities = dict(zip(OUTCOME_LABELS, values, strict=True))
        expected_r = calculate_expected_r(
            probabilities,
            estimated_cost_r=estimated_cost_r,
        )
    except MLError as exc:
        return PredictionResult(
            model_name=model_name,
            model_version=model_version,
            feature_schema_version=schema.version,
            probabilities={label: 0.0 for label in OUTCOME_LABELS},
            expected_r=0.0,
            accepted=False,
            reason=f"abstain:{type(exc).__name__}",
        )
    except Exception:
        # Model-library failures are deliberately collapsed to a stable reason;
        # callers should log operational detail without exposing it to users.
        return PredictionResult(
            model_name=model_name,
            model_version=model_version,
            feature_schema_version=schema.version,
            probabilities={label: 0.0 for label in OUTCOME_LABELS},
            expected_r=0.0,
            accepted=False,
            reason="abstain:InferenceError",
        )

    accepted = expected_r >= minimum_expected_r
    return PredictionResult(
        model_name=model_name,
        model_version=model_version,
        feature_schema_version=schema.version,
        probabilities=probabilities,
        expected_r=expected_r,
        accepted=accepted,
        reason="expected_r_above_threshold" if accepted else "expected_r_below_threshold",
    )
