import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from ml.data.load_dataset import PROJECT_ROOT
from ml.replay.replay_export import _checksum
from ml.training_dataset.builder import MODEL_FEATURE_COLUMNS, TARGET_COLUMNS, TARGET_METADATA_COLUMNS
from ml.training_dataset.config import PARTITION_COLUMNS


def _safe(path):
    allowed = (PROJECT_ROOT / "ml" / "data" / "datasets").resolve(); resolved = path.resolve()
    try: resolved.relative_to(allowed)
    except ValueError as exc: raise ValueError("Training output must remain under ml/data/datasets") from exc
    if resolved == allowed: raise ValueError("Training output cannot be datasets root")
    return resolved


def _write(frame, root, partitions, basename, compression):
    import pyarrow as pa
    import pyarrow.dataset as ds
    root.mkdir(parents=True, exist_ok=False)
    ordered = frame.sort_values([column for column in ("candidate_timestamp", "candidate_id", "fold") if column in frame], kind="mergesort")
    fmt = ds.ParquetFileFormat(); options = fmt.make_write_options(compression=compression)
    ds.write_dataset(pa.Table.from_pandas(ordered, preserve_index=False), base_dir=root, format=fmt, file_options=options,
                     partitioning=list(partitions), partitioning_flavor="hive", basename_template=f"{basename}-part-{{i}}.parquet",
                     existing_data_behavior="error", use_threads=False)
    return tuple(sorted(root.rglob("*.parquet")))


def export_training(result, config, overwrite=False):
    import pandas as pd
    output = _safe(config.dataset_root)
    if output.exists() and not overwrite: raise FileExistsError(f"Training dataset exists: {output}; pass --overwrite")
    backup = output.with_name(f".{output.name}.previous")
    if backup.exists(): raise FileExistsError(f"Stale backup requires review: {backup}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".training-v1-", dir=output.parent) as temporary:
        staged = Path(temporary) / output.name
        dataset = result.dataset.copy(); dataset["year"] = pd.to_datetime(dataset.candidate_timestamp, utc=True).dt.year.astype("int16")
        files = list(_write(dataset, staged / "dataset", PARTITION_COLUMNS, "training", config.compression))
        files += list(_write(result.split_assignments, staged / "split_assignments", ("split",), "splits", config.compression))
        files += list(_write(result.walk_forward_assignments, staged / "walk_forward", ("fold", "role"), "walk", config.compression))
        files = tuple(sorted(files)); checksum = _checksum(staged, files)
        identity = json.dumps({"feature": result.feature_manifest["feature_dataset_id"], "outcome": result.outcome_manifest["outcome_dataset_id"], "policy": config.version, "checksum": checksum}, sort_keys=True)
        manifest = {
            "training_dataset_id": f"sha256:{hashlib.sha256(identity.encode()).hexdigest()}", "created_at": datetime.now(timezone.utc).isoformat(),
            "training_policy_version": config.version, "feature_dataset_id": result.feature_manifest["feature_dataset_id"],
            "feature_dataset_checksum": result.feature_manifest["checksum"], "outcome_dataset_id": result.outcome_manifest["outcome_dataset_id"],
            "outcome_dataset_checksum": result.outcome_manifest["checksum"], "candidate_dataset_id": result.feature_manifest["candidate_dataset_id"],
            "candidate_dataset_checksum": result.feature_manifest["candidate_dataset_checksum"], "row_count": len(result.dataset),
            "unique_candidate_ids": int(result.dataset.candidate_id.nunique()), "supervised_eligible_count": int(result.dataset.supervised_eligible.sum()),
            "model_feature_columns": list(MODEL_FEATURE_COLUMNS), "target_columns": list(TARGET_COLUMNS),
            "future_derived_metadata_columns": list(TARGET_METADATA_COLUMNS),
            "binary_success_rule": "net_realized_r > 0; zero and negative are failures; right-censored is null/ineligible",
            "split_counts": result.dataset.split.value_counts().sort_index().to_dict(), "split_policy": result.split_policy,
            "walk_forward_folds": config.walk_forward_folds, "partition_columns": list(PARTITION_COLUMNS),
            "file_count": len(files), "checksum": checksum,
        }
        (staged / "training_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", "utf-8")
        if output.exists(): output.replace(backup)
        try: staged.replace(output)
        except Exception:
            if backup.exists() and not output.exists(): backup.replace(output)
            raise
        if backup.exists(): shutil.rmtree(backup)
    return output, tuple(sorted(output.rglob("*.parquet"))), manifest
