"""Clean and export the validated XAUUSD dataset as partitioned Parquet."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Iterable, Mapping

from ml.data.clean_dataset import CleanedDataset, clean_dataset
from ml.data.inspect_dataset import inspect_dataset, write_reports
from ml.data.load_dataset import (
    DEFAULT_CONFIG_PATH,
    PROJECT_ROOT,
    DatasetConfig,
    HubInventory,
    inspect_hub_inventory,
    iter_timeframe_datasets,
    load_config,
)
from ml.data.validate_dataset import CANONICAL_COLUMNS, DatasetValidationError


MANIFEST_NAME = "dataset_manifest.json"


def _git_commit() -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def _dataset_checksum(root: Path, parquet_files: tuple[Path, ...]) -> str:
    digest = hashlib.sha256()
    for path in parquet_files:
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def _validate_output_root(config: DatasetConfig) -> Path:
    allowed_root = (PROJECT_ROOT / "ml" / "data" / "processed").resolve()
    output = config.output_root.resolve()
    try:
        output.relative_to(allowed_root)
    except ValueError as exc:
        raise DatasetValidationError(
            f"Output must remain inside {allowed_root}: {output}"
        ) from exc
    if output == allowed_root:
        raise DatasetValidationError("Output must be a dataset directory, not processed/")
    return output


def add_partition_year(candles):
    """Derive the sole non-canonical export field from normalized UTC time."""
    result = candles.copy()
    result["year"] = result["timestamp"].dt.year.astype("int16")
    return result


def write_partitioned_parquet(
    cleaned_by_timeframe: Mapping[str, CleanedDataset],
    *,
    destination: Path,
    config: DatasetConfig,
) -> tuple[Path, ...]:
    """Write deterministic Hive partitions without duplicating partition columns."""
    import pyarrow as pa
    import pyarrow.dataset as ds

    destination.mkdir(parents=True, exist_ok=False)
    parquet_format = ds.ParquetFileFormat()
    options = parquet_format.make_write_options(compression=config.compression)
    for timeframe in sorted(cleaned_by_timeframe):
        frame = add_partition_year(cleaned_by_timeframe[timeframe].candles)
        table = pa.Table.from_pandas(frame, preserve_index=False)
        ds.write_dataset(
            table,
            base_dir=destination,
            format=parquet_format,
            file_options=options,
            partitioning=list(config.partition_columns),
            partitioning_flavor="hive",
            basename_template=f"{timeframe.lower()}-part-{{i}}.parquet",
            existing_data_behavior="overwrite_or_ignore",
        )
    return tuple(sorted(destination.rglob("*.parquet")))


def build_manifest(
    *,
    config: DatasetConfig,
    inventory: HubInventory,
    cleaned_by_timeframe: Mapping[str, CleanedDataset],
    validation_report_path: Path,
    output_root: Path,
    parquet_files: tuple[Path, ...],
) -> dict:
    rows_by_timeframe = {
        timeframe: len(cleaned.candles)
        for timeframe, cleaned in sorted(cleaned_by_timeframe.items())
    }
    starts = [
        cleaned.candles["timestamp"].min()
        for cleaned in cleaned_by_timeframe.values()
        if not cleaned.candles.empty
    ]
    ends = [
        cleaned.candles["timestamp"].max()
        for cleaned in cleaned_by_timeframe.values()
        if not cleaned.candles.empty
    ]
    try:
        report_reference = validation_report_path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        report_reference = str(validation_report_path.resolve())
    checksum = _dataset_checksum(output_root, parquet_files)
    dataset_identity = json.dumps({
        "dataset_name": config.dataset_name,
        "resolved_revision": inventory.resolved_revision or config.revision,
        "checksum": checksum,
    }, sort_keys=True, separators=(",", ":"))
    dataset_id = f"sha256:{hashlib.sha256(dataset_identity.encode()).hexdigest()}"
    return {
        "dataset_id": dataset_id,
        "dataset_name": config.dataset_name,
        "dataset_revision": config.revision,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "symbol": config.symbol,
        "timeframes": sorted(rows_by_timeframe),
        "row_count": sum(rows_by_timeframe.values()),
        "rows_by_timeframe": rows_by_timeframe,
        "timestamp_start": min(starts).isoformat() if starts else None,
        "timestamp_end": max(ends).isoformat() if ends else None,
        "canonical_columns": list(CANONICAL_COLUMNS),
        "partition_columns": list(config.partition_columns),
        "validation_report": report_reference,
        "source_commit": _git_commit(),
        "huggingface_resolved_revision": inventory.resolved_revision,
        "cleaning_config": config.cleaning_settings(),
        "file_count": len(parquet_files),
        "checksum": checksum,
    }


def export_cleaned_dataset(
    cleaned_by_timeframe: Mapping[str, CleanedDataset],
    *,
    config: DatasetConfig,
    inventory: HubInventory,
    validation_report_path: Path,
    overwrite: bool = False,
) -> Path:
    """Build a complete dataset before an explicit, rollback-safe replacement."""
    output = _validate_output_root(config)
    if output.exists() and not overwrite:
        raise FileExistsError(
            f"Export already exists: {output}. Pass --overwrite to replace it explicitly."
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    backup = output.with_name(f".{output.name}.previous")
    if backup.exists():
        raise FileExistsError(f"Stale export backup requires review: {backup}")

    with TemporaryDirectory(prefix=f".{output.name}-", dir=output.parent) as temporary:
        staged = Path(temporary) / output.name
        parquet_files = write_partitioned_parquet(
            cleaned_by_timeframe,
            destination=staged,
            config=config,
        )
        manifest = build_manifest(
            config=config,
            inventory=inventory,
            cleaned_by_timeframe=cleaned_by_timeframe,
            validation_report_path=validation_report_path,
            output_root=staged,
            parquet_files=parquet_files,
        )
        (staged / MANIFEST_NAME).write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
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
    return output


def run_export(config: DatasetConfig, *, overwrite: bool = False) -> Path:
    """Inspect, report, safely clean, and export every trusted timeframe file."""
    inventory = inspect_hub_inventory(config)
    inspection = inspect_dataset(config, inventory)
    json_report, _ = write_reports(inspection, config.report_root)
    if inspection.validation_errors:
        raise DatasetValidationError(
            f"Dataset inspection failed: {inspection.validation_errors!r}"
        )

    cleaned: dict[str, CleanedDataset] = {}
    for loaded in iter_timeframe_datasets(config, inventory):
        frame = loaded.dataset.to_pandas()
        cleaned[loaded.timeframe] = clean_dataset(
            frame,
            config=config,
            timeframe=loaded.timeframe,
            source_name=loaded.source_file,
        )
    return export_cleaned_dataset(
        cleaned,
        config=config,
        inventory=inventory,
        validation_report_path=json_report,
        overwrite=overwrite,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export validated XAUUSD Parquet data")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = load_config(args.config)
    output = run_export(config, overwrite=args.overwrite)
    print(json.dumps({"output": str(output)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
