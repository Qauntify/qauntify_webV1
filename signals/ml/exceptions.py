"""Exceptions raised by the production ML inference boundary."""


class MLError(Exception):
    """Base class for ML inference errors that callers may handle safely."""


class FeatureSchemaError(MLError):
    """Live features do not match the model's declared feature schema."""


class ArtifactError(MLError):
    """An approved model artifact cannot be resolved or verified."""


class InferenceError(MLError):
    """A loaded model returned an invalid or unusable prediction."""
