import json

import pytest

import ml.replay.replay_export as export_module
from ml.replay.candidate_builder import build_candidate
from ml.replay.replay_export import CANDIDATE_MANIFEST, export_candidates


def _candidate(setup, strategy="ict_fvg"):
    return build_candidate(
        setup,
        candidate_timestamp="2024-01-02T00:05:00+00:00",
        source_candle_timestamp="2024-01-02T00:00:00+00:00",
        timeframe="M5", strategy_name=strategy,
        strategy_version="sha256:fixture", dataset_id="dataset-fixture",
        dataset_checksum="abc123", replay_config_version="replay_v1",
        source_commit="commit-fixture",
    )


def test_partition_export_manifest_and_safe_overwrite(
    tmp_path, monkeypatch, long_setup, source_manifest,
):
    pytest.importorskip("pyarrow")
    project = tmp_path / "repo"
    output = project / "ml/data/processed/candidates"
    monkeypatch.setattr(export_module, "PROJECT_ROOT", project)
    candidate = _candidate(long_setup)

    exported, files = export_candidates(
        (candidate,), output=output, source_manifest=source_manifest,
        config_version="replay_v1",
    )
    assert len(files) == 1
    relative = files[0].relative_to(exported).as_posix()
    assert relative.startswith("symbol=XAUUSD/timeframe=M5/strategy_name=ict_fvg/year=2024/")
    manifest = json.loads((exported / CANDIDATE_MANIFEST).read_text("utf-8"))
    assert manifest["candidate_count"] == 1
    assert manifest["source_dataset_id"] == "dataset-fixture"
    assert manifest["file_count"] == 1
    assert len(manifest["checksum"]) == 64

    with pytest.raises(FileExistsError, match="--overwrite"):
        export_candidates(
            (candidate,), output=output, source_manifest=source_manifest,
            config_version="replay_v1",
        )
    replaced, _ = export_candidates(
        (candidate,), output=output, source_manifest=source_manifest,
        config_version="replay_v1", overwrite=True,
    )
    assert replaced == exported
    assert not output.with_name(".candidates.previous").exists()


def test_multiple_strategies_can_emit_on_same_candle(long_setup, short_setup):
    first = _candidate(long_setup, "ict_fvg")
    second = _candidate(short_setup, "sr_zone")
    assert first.candidate_timestamp == second.candidate_timestamp
    assert first.candidate_id != second.candidate_id

