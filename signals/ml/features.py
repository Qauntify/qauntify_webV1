"""Canonical, production-safe candidate feature construction.

Training code imports this module directly so offline and live calculations do
not develop separate implementations.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence

from signals.ml.exceptions import FeatureSchemaError
from signals.ml.feature_schema import FeatureValue


@dataclass(frozen=True)
class CandidateFeatureInput:
    """Information available at the instant a strategy emits a candidate."""

    symbol: str
    timeframe: str
    session: str
    strategy: str
    direction: str
    entry: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    take_profit_3: float
    indicators: Mapping[str, FeatureValue | None] = field(default_factory=dict)


def _base_features(candidate: CandidateFeatureInput) -> dict[str, FeatureValue]:
    risk = abs(candidate.entry - candidate.stop_loss)
    if risk == 0:
        raise FeatureSchemaError("Candidate entry and stop_loss must differ")

    return {
        "symbol": candidate.symbol,
        "timeframe": candidate.timeframe,
        "session": candidate.session,
        "strategy": candidate.strategy,
        "direction": candidate.direction,
        "risk_distance": float(risk),
        "tp1_r": float(abs(candidate.take_profit_1 - candidate.entry) / risk),
        "tp2_r": float(abs(candidate.take_profit_2 - candidate.entry) / risk),
        "tp3_r": float(abs(candidate.take_profit_3 - candidate.entry) / risk),
    }


def build_candidate_features(
    candidate: CandidateFeatureInput,
    *,
    feature_order: Sequence[str] | None = None,
) -> dict[str, FeatureValue]:
    """Build one deterministic feature row from a candidate-time snapshot.

    Scalar detector indicators are namespaced as ``indicator.<name>`` and
    sorted. A supplied model feature order is enforced without filling missing
    values or silently dropping unknown fields.
    """
    features = _base_features(candidate)
    for name in sorted(candidate.indicators):
        value = candidate.indicators[name]
        if value is None:
            continue
        if not isinstance(value, (bool, float, int, str)):
            raise FeatureSchemaError(
                f"Indicator {name!r} has unsupported type {type(value).__name__}"
            )
        features[f"indicator.{name}"] = value

    if feature_order is None:
        return features

    expected = tuple(feature_order)
    missing = tuple(name for name in expected if name not in features)
    extra = tuple(name for name in features if name not in expected)
    if missing or extra:
        raise FeatureSchemaError(
            f"Feature-set mismatch: missing={missing!r}, extra={extra!r}"
        )
    return {name: features[name] for name in expected}
