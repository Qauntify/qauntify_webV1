"""Stable project paths and verified loading for approved model artifacts."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, TypeVar

from signals.ml.exceptions import ArtifactError


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS_ROOT = PROJECT_ROOT / "artifacts"
ACTIVE_ARTIFACTS_ROOT = ARTIFACTS_ROOT / "active"
LEGACY_LSTM_ROOT = ARTIFACTS_ROOT / "legacy_lstm"
LEGACY_LSTM_SCALERS_ROOT = LEGACY_LSTM_ROOT / "scalers"

T = TypeVar("T")


@dataclass(frozen=True)
class ArtifactLocation:
    """Repository-relative location and optional integrity checksum."""

    relative_path: str
    sha256: str | None = None


def resolve_artifact_path(
    relative_path: str,
    *,
    artifacts_root: Path = ARTIFACTS_ROOT,
) -> Path:
    """Resolve an artifact path without depending on the process working directory."""
    candidate = Path(relative_path)
    if candidate.is_absolute():
        raise ArtifactError("Artifact paths must be relative to artifacts/")

    root = artifacts_root.resolve()
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ArtifactError("Artifact path escapes artifacts/") from exc
    return resolved


def sha256_file(path: Path) -> str:
    """Calculate a model artifact checksum without deserializing it."""
    digest = hashlib.sha256()
    with path.open("rb") as artifact:
        for chunk in iter(lambda: artifact.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_model_artifact(
    location: ArtifactLocation,
    *,
    loader: Callable[[Path], T],
    artifacts_root: Path = ARTIFACTS_ROOT,
) -> T:
    """Verify a trusted local artifact, then delegate format-specific loading.

    The caller must provide a safe loader for the approved format. This module
    deliberately does not unpickle arbitrary files or import training libraries.
    """
    path = resolve_artifact_path(location.relative_path, artifacts_root=artifacts_root)
    if not path.is_file():
        raise ArtifactError(f"Model artifact does not exist: {path}")
    if location.sha256 and sha256_file(path) != location.sha256.lower():
        raise ArtifactError(f"Checksum mismatch for model artifact: {path}")
    try:
        return loader(path)
    except ArtifactError:
        raise
    except Exception as exc:
        raise ArtifactError(f"Unable to load approved model artifact: {path}") from exc
