import hashlib

import pytest

from signals.ml.exceptions import ArtifactError
from signals.ml.registry import ArtifactLocation, load_model_artifact, resolve_artifact_path


def test_load_model_artifact_verifies_checksum_before_delegating(tmp_path):
    artifact = tmp_path / "active" / "model.cbm"
    artifact.parent.mkdir()
    artifact.write_bytes(b"approved model bytes")
    checksum = hashlib.sha256(artifact.read_bytes()).hexdigest()

    loaded = load_model_artifact(
        ArtifactLocation("active/model.cbm", checksum),
        loader=lambda path: path.read_bytes(),
        artifacts_root=tmp_path,
    )

    assert loaded == b"approved model bytes"


def test_model_loading_rejects_bad_checksum_and_path_escape(tmp_path):
    artifact = tmp_path / "model.cbm"
    artifact.write_bytes(b"bytes")

    with pytest.raises(ArtifactError, match="Checksum mismatch"):
        load_model_artifact(
            ArtifactLocation("model.cbm", "0" * 64),
            loader=lambda path: path,
            artifacts_root=tmp_path,
        )

    with pytest.raises(ArtifactError, match="escapes"):
        resolve_artifact_path("../outside.cbm", artifacts_root=tmp_path)
