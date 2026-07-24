"""Deterministic, partitioned, rollback-safe candidate export."""
from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from ml.data.load_dataset import PROJECT_ROOT
from ml.replay.candidate_schema import PARTITION_COLUMNS, validate_candidates


CANDIDATE_MANIFEST = "candidate_manifest.json"


def _checksum(root: Path, files: tuple[Path, ...]) -> str:
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.relative_to(root).as_posix().encode())
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def _safe_output(output: Path) -> Path:
    allowed = (PROJECT_ROOT / "ml" / "data" / "processed").resolve()
    resolved = output.resolve()
    try:
        resolved.relative_to(allowed)
    except ValueError as exc:
        raise ValueError(f"Candidate output must remain inside {allowed}") from exc
    if resolved == allowed:
        raise ValueError("Candidate output cannot be the processed data root")
    return resolved


def write_candidate_parquet(candidates, destination: Path, compression="zstd") -> tuple[Path, ...]:
    import pandas as pd
    import pyarrow as pa
    import pyarrow.dataset as ds

    validate_candidates(candidates)
    destination.mkdir(parents=True, exist_ok=False)
    if not candidates:
        return ()
    frame = pd.DataFrame(candidate.to_dict() for candidate in candidates)
    frame["candidate_timestamp"] = pd.to_datetime(frame["candidate_timestamp"], utc=True)
    frame["source_candle_timestamp"] = pd.to_datetime(frame["source_candle_timestamp"], utc=True)
    frame["created_at"] = pd.to_datetime(frame["created_at"], utc=True)
    frame["year"] = frame["candidate_timestamp"].dt.year.astype("int16")
    frame = frame.sort_values(["symbol", "timeframe", "strategy_name", "candidate_timestamp"])
    parquet_format = ds.ParquetFileFormat()
    options = parquet_format.make_write_options(compression=compression)
    ds.write_dataset(
        pa.Table.from_pandas(frame, preserve_index=False),
        base_dir=destination,
        format=parquet_format,
        file_options=options,
        partitioning=list(PARTITION_COLUMNS),
        partitioning_flavor="hive",
        basename_template="candidates-part-{i}.parquet",
        existing_data_behavior="error",
    )
    return tuple(sorted(destination.rglob("*.parquet")))


def build_candidate_manifest(candidates, *, source_manifest, config_version, root, files) -> dict:
    import pandas as pd

    timestamps = [pd.Timestamp(candidate.candidate_timestamp) for candidate in candidates]
    checksum = _checksum(root, files)
    identity = json.dumps({
        "source_dataset_id": source_manifest["dataset_id"],
        "source_dataset_checksum": source_manifest["checksum"],
        "replay_config_version": config_version,
        "checksum": checksum,
    }, sort_keys=True, separators=(",", ":"))
    candidate_dataset_id = f"sha256:{hashlib.sha256(identity.encode()).hexdigest()}"
    from collections import Counter
    return {
        "candidate_dataset_id": candidate_dataset_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_dataset_id": source_manifest["dataset_id"],
        "source_dataset_checksum": source_manifest["checksum"],
        "source_commit": source_manifest.get("source_commit"),
        "replay_config_version": config_version,
        "symbols": sorted({candidate.symbol for candidate in candidates}),
        "timeframes": sorted({candidate.timeframe for candidate in candidates}),
        "strategies": sorted({candidate.strategy_name for candidate in candidates}),
        "candidate_count": len(candidates),
        "candidates_by_timeframe": dict(sorted(Counter(c.timeframe for c in candidates).items())),
        "candidates_by_strategy": dict(sorted(Counter(c.strategy_name for c in candidates).items())),
        "timestamp_start": min(timestamps).isoformat() if timestamps else None,
        "timestamp_end": max(timestamps).isoformat() if timestamps else None,
        "partition_columns": list(PARTITION_COLUMNS),
        "file_count": len(files),
        "checksum": checksum,
    }


def export_candidates(candidates, *, output: Path, source_manifest, config_version: str,
                      compression="zstd", overwrite=False) -> tuple[Path, tuple[Path, ...]]:
    output = _safe_output(output)
    if output.exists() and not overwrite:
        raise FileExistsError(f"Candidate export exists: {output}; pass --overwrite")
    output.parent.mkdir(parents=True, exist_ok=True)
    backup = output.with_name(f".{output.name}.previous")
    if backup.exists():
        raise FileExistsError(f"Stale candidate backup requires review: {backup}")
    with TemporaryDirectory(prefix=f".{output.name}-", dir=output.parent) as temporary:
        staged = Path(temporary) / output.name
        files = write_candidate_parquet(candidates, staged, compression)
        manifest = build_candidate_manifest(
            candidates, source_manifest=source_manifest,
            config_version=config_version, root=staged, files=files,
        )
        (staged / CANDIDATE_MANIFEST).write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", "utf-8"
        )
        if output.exists():
            output.replace(backup)
        try:
            staged.replace(output)
        except Exception:
            if backup.exists() and not output.exists():
                backup.replace(output)
            raise
        if backup.exists():
            shutil.rmtree(backup)
    return output, tuple(sorted(output.rglob("*.parquet")))

