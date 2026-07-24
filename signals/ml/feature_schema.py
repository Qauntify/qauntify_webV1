"""Versioned feature-schema types and validation for training and inference."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Mapping, Sequence

from signals.ml.exceptions import FeatureSchemaError


FeatureKind = Literal["bool", "float", "int", "str"]
FeatureValue = bool | float | int | str
FEATURE_SCHEMA_VERSION = "v1"


@dataclass(frozen=True)
class FeatureSpec:
    """One ordered feature expected by an approved model artifact."""

    name: str
    kind: FeatureKind


@dataclass(frozen=True)
class FeatureSchema:
    """The exact names, ordering, and primitive types used by a model."""

    version: str
    features: tuple[FeatureSpec, ...]

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(feature.name for feature in self.features)


def _matches_kind(value: FeatureValue, kind: FeatureKind) -> bool:
    if kind == "bool":
        return isinstance(value, bool)
    if kind == "float":
        return isinstance(value, float)
    if kind == "int":
        return isinstance(value, int) and not isinstance(value, bool)
    return isinstance(value, str)


def infer_feature_kind(value: FeatureValue) -> FeatureKind:
    """Return the non-coercing primitive kind used in exported schemas."""
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, float):
        return "float"
    if isinstance(value, int):
        return "int"
    if isinstance(value, str):
        return "str"
    raise FeatureSchemaError(f"Unsupported feature value type: {type(value).__name__}")


def schema_from_features(
    features: Mapping[str, FeatureValue],
    *,
    version: str = FEATURE_SCHEMA_VERSION,
) -> FeatureSchema:
    """Build a schema from an already ordered feature mapping."""
    return FeatureSchema(
        version=version,
        features=tuple(
            FeatureSpec(name=name, kind=infer_feature_kind(value))
            for name, value in features.items()
        ),
    )


def validate_feature_schema(
    features: Mapping[str, FeatureValue],
    schema: FeatureSchema,
) -> None:
    """Require exact feature names, ordering, and primitive value types."""
    actual_names = tuple(features)
    if actual_names != schema.names:
        raise FeatureSchemaError(
            f"Feature order mismatch: expected {schema.names!r}, got {actual_names!r}"
        )

    for spec in schema.features:
        value = features[spec.name]
        if not _matches_kind(value, spec.kind):
            raise FeatureSchemaError(
                f"Feature {spec.name!r} must be {spec.kind}, "
                f"got {type(value).__name__}"
            )


def feature_schema_from_records(
    version: str,
    records: Sequence[Mapping[str, str]],
) -> FeatureSchema:
    """Parse JSON-compatible schema records without loading executable data."""
    valid_kinds = {"bool", "float", "int", "str"}
    specs = []
    for record in records:
        name = record.get("name")
        kind = record.get("kind")
        if not name or kind not in valid_kinds:
            raise FeatureSchemaError(f"Invalid feature schema record: {record!r}")
        specs.append(FeatureSpec(name=name, kind=kind))  # type: ignore[arg-type]
    return FeatureSchema(version=version, features=tuple(specs))
