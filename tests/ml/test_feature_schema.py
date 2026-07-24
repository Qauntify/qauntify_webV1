import pytest

from signals.ml.exceptions import FeatureSchemaError
from signals.ml.feature_schema import schema_from_features, validate_feature_schema


def test_validate_feature_schema_requires_exact_order_and_types():
    features = {"symbol": "XAUUSD", "risk": 1.5, "count": 2, "active": True}
    schema = schema_from_features(features)

    validate_feature_schema(features, schema)

    with pytest.raises(FeatureSchemaError, match="order mismatch"):
        validate_feature_schema(dict(reversed(tuple(features.items()))), schema)

    with pytest.raises(FeatureSchemaError, match="must be float"):
        validate_feature_schema({**features, "risk": 1}, schema)
