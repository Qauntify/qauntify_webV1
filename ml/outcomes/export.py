"""Safe partitioned export and manifest generation for outcome_v1."""
from __future__ import annotations

import hashlib
import json
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from ml.data.load_dataset import PROJECT_ROOT
from ml.outcomes.schema import PARTITION_COLUMNS, validate_outcomes
from ml.replay.replay_export import _checksum


OUTCOME_MANIFEST = "outcome_manifest.json"


def _safe_output(path: Path) -> Path:
    allowed = (PROJECT_ROOT / "ml" / "data" / "processed").resolve()
    resolved = path.resolve()
    try:
        resolved.relative_to(allowed)
    except ValueError as exc:
        raise ValueError(f"Outcome output must remain inside {allowed}") from exc
    if resolved == allowed:
        raise ValueError("Outcome output cannot be the processed root")
    return resolved


def write_outcome_parquet(outcomes, destination: Path, compression="zstd") -> tuple[Path, ...]:
    import pandas as pd
    import pyarrow as pa
    import pyarrow.dataset as ds

    validate_outcomes(outcomes)
    destination.mkdir(parents=True, exist_ok=False)
    if not outcomes:
        return ()
    frame = pd.DataFrame(outcome.to_dict() for outcome in outcomes)
    timestamp_columns = [
        "entry_triggered_at", "tp1_hit_at", "tp2_hit_at", "tp3_hit_at",
        "sl_hit_at", "expiry_at", "resolution_timestamp", "created_at",
    ]
    for column in timestamp_columns:
        frame[column] = pd.to_datetime(frame[column], utc=True)
    frame["year"] = frame["entry_triggered_at"].dt.year.astype("int16")
    frame = frame.sort_values(["strategy_name", "timeframe", "entry_triggered_at", "candidate_id"])
    parquet_format = ds.ParquetFileFormat()
    options = parquet_format.make_write_options(compression=compression)
    ds.write_dataset(
        pa.Table.from_pandas(frame, preserve_index=False),
        base_dir=destination,
        format=parquet_format,
        file_options=options,
        partitioning=list(PARTITION_COLUMNS),
        partitioning_flavor="hive",
        basename_template="outcomes-part-{i}.parquet",
        existing_data_behavior="error",
    )
    return tuple(sorted(destination.rglob("*.parquet")))


def build_manifest(outcomes, *, result, config, root, files) -> dict:
    import pandas as pd

    checksum = _checksum(root, files)
    identity = json.dumps({
        "candidate_dataset_id": result.candidate_manifest["candidate_dataset_id"],
        "candidate_dataset_checksum": result.candidate_manifest["checksum"],
        "policy": config.version,
        "checksum": checksum,
    }, sort_keys=True, separators=(",", ":"))
    outcome_dataset_id = f"sha256:{hashlib.sha256(identity.encode()).hexdigest()}"
    timestamps = [pd.Timestamp(outcome.entry_triggered_at) for outcome in outcomes]
    return {
        "outcome_dataset_id": outcome_dataset_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "outcome_policy_version": config.version,
        "candidate_dataset_id": result.candidate_manifest["candidate_dataset_id"],
        "candidate_dataset_checksum": result.candidate_manifest["checksum"],
        "source_dataset_id": result.candle_manifest["dataset_id"],
        "source_dataset_checksum": result.candle_manifest["checksum"],
        "source_commit": result.candidate_manifest.get("source_commit"),
        "outcome_count": len(outcomes),
        "outcomes_by_class": dict(sorted(Counter(o.outcome_class for o in outcomes).items())),
        "outcomes_by_strategy": dict(sorted(Counter(o.strategy_name for o in outcomes).items())),
        "outcomes_by_timeframe": dict(sorted(Counter(o.timeframe for o in outcomes).items())),
        "timestamp_start": min(timestamps).isoformat() if timestamps else None,
        "timestamp_end": max(timestamps).isoformat() if timestamps else None,
        "partition_columns": list(PARTITION_COLUMNS),
        "file_count": len(files),
        "checksum": checksum,
        "policy": {
            "entry": "market_on_candidate_close",
            "stop": "fixed_initial_stop",
            "take_profit_fractions": list(config.take_profit_fractions),
            "expiry_days": config.expiry_days,
            "lower_timeframes": config.lower_timeframes,
            "same_candle_fallback": "stop_first_conservative",
            "estimated_round_trip_cost_r": config.estimated_round_trip_cost_r,
        },
    }


def export_outcomes(result, *, config, overwrite=False):
    output = _safe_output(config.outcomes_root)
    if output.exists() and not overwrite:
        raise FileExistsError(f"Outcome export exists: {output}; pass --overwrite")
    output.parent.mkdir(parents=True, exist_ok=True)
    backup = output.with_name(f".{output.name}.previous")
    if backup.exists():
        raise FileExistsError(f"Stale outcome backup requires review: {backup}")
    with TemporaryDirectory(prefix=f".{output.name}-", dir=output.parent) as temporary:
        staged = Path(temporary) / output.name
        files = write_outcome_parquet(result.outcomes, staged, config.compression)
        manifest = build_manifest(
            result.outcomes, result=result, config=config, root=staged, files=files,
        )
        (staged / OUTCOME_MANIFEST).write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", "utf-8",
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

