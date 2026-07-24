"""Atomic partitioned Parquet export for feature_v1."""
from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from ml.data.load_dataset import PROJECT_ROOT
from ml.features.config import PARTITION_COLUMNS
from ml.features.schema import NUMERIC_FEATURES, validate_features
from ml.replay.replay_export import _checksum


def _safe_output(path: Path):
    allowed = (PROJECT_ROOT / "ml" / "data" / "processed").resolve()
    resolved = path.resolve()
    try: resolved.relative_to(allowed)
    except ValueError as exc: raise ValueError("Feature output must remain in processed data") from exc
    if resolved == allowed: raise ValueError("Feature output cannot be the processed root")
    return resolved


def write_parquet(features, destination, compression):
    import pandas as pd
    import pyarrow as pa
    import pyarrow.dataset as ds
    validate_features(features)
    destination.mkdir(parents=True, exist_ok=False)
    frame = pd.DataFrame(features)
    for column in ("candidate_timestamp", "source_candle_timestamp"):
        frame[column] = pd.to_datetime(frame[column], utc=True)
    frame["year"] = frame.candidate_timestamp.dt.year.astype("int16")
    frame = frame.sort_values(["strategy_name", "timeframe", "candidate_timestamp", "candidate_id"])
    fmt = ds.ParquetFileFormat(); options = fmt.make_write_options(compression=compression)
    ds.write_dataset(pa.Table.from_pandas(frame, preserve_index=False), base_dir=destination,
                     format=fmt, file_options=options, partitioning=list(PARTITION_COLUMNS),
                     partitioning_flavor="hive", basename_template="features-part-{i}.parquet",
                     existing_data_behavior="error")
    return tuple(sorted(destination.rglob("*.parquet")))


def export_features(result, config, overwrite=False):
    output = _safe_output(config.features_root)
    if output.exists() and not overwrite: raise FileExistsError(f"Feature export exists: {output}; pass --overwrite")
    backup = output.with_name(f".{output.name}.previous")
    if backup.exists(): raise FileExistsError(f"Stale feature backup requires review: {backup}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=f".{output.name}-", dir=output.parent) as temporary:
        staged = Path(temporary) / output.name
        files = write_parquet(result.features, staged, config.compression)
        checksum = _checksum(staged, files)
        identity = json.dumps({"candidate_dataset_id": result.candidate_manifest["candidate_dataset_id"], "policy": config.version, "checksum": checksum}, sort_keys=True)
        manifest = {
            "feature_dataset_id": f"sha256:{hashlib.sha256(identity.encode()).hexdigest()}",
            "created_at": datetime.now(timezone.utc).isoformat(), "feature_policy_version": config.version,
            "candidate_dataset_id": result.candidate_manifest["candidate_dataset_id"],
            "candidate_dataset_checksum": result.candidate_manifest["checksum"],
            "source_dataset_id": result.candle_manifest["dataset_id"], "source_dataset_checksum": result.candle_manifest["checksum"],
            "source_commit": result.candidate_manifest.get("source_commit"), "feature_count": len(result.features),
            "feature_columns": list(NUMERIC_FEATURES), "partition_columns": list(PARTITION_COLUMNS),
            "file_count": len(files), "checksum": checksum,
            "causality": {"boundary": "source_candle_close", "future_candles_used": False},
        }
        (staged / "feature_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", "utf-8")
        if output.exists(): output.replace(backup)
        try: staged.replace(output)
        except Exception:
            if backup.exists() and not output.exists(): backup.replace(output)
            raise
        if backup.exists(): shutil.rmtree(backup)
    return output, tuple(sorted(output.rglob("*.parquet"))), manifest

