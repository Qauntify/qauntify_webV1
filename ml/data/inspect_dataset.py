"""CLI and report generation for the Hugging Face XAUUSD dataset."""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from ml.data.load_dataset import (
    DEFAULT_CONFIG_PATH,
    DatasetConfig,
    HubInventory,
    inspect_hub_inventory,
    iter_timeframe_datasets,
    load_config,
)
from ml.data.validate_dataset import DatasetValidationError, validate_dataset


@dataclass(frozen=True)
class DatasetInspectionReport:
    created_at: str
    hub: dict
    total_rows: int
    rows_by_split: dict[str, int | None]
    rows_by_timeframe: dict[str, int]
    detected_timeframes: tuple[str, ...]
    samples_by_timeframe: dict[str, list[dict]]
    validations: dict[str, dict]
    validation_errors: dict[str, str]
    timestamp_start: str | None
    timestamp_end: str | None
    total_memory_bytes: int

    def to_dict(self) -> dict:
        return asdict(self)


def _json_safe_records(frame, limit: int) -> list[dict]:
    records = frame.head(limit).to_dict(orient="records")
    return json.loads(json.dumps(records, default=str))


def inspect_dataset(
    config: DatasetConfig,
    inventory: HubInventory,
    *,
    sample_rows: int = 5,
) -> DatasetInspectionReport:
    """Inspect and fully validate each source file without cleaning or export."""
    if sample_rows <= 0:
        raise ValueError("sample_rows must be positive")

    total_rows = 0
    total_memory = 0
    rows_by_timeframe: dict[str, int] = {}
    samples: dict[str, list[dict]] = {}
    validations: dict[str, dict] = {}
    validation_errors: dict[str, str] = {}
    starts: list[str] = []
    ends: list[str] = []

    for loaded in iter_timeframe_datasets(config, inventory):
        frame = loaded.dataset.to_pandas()  # Arrow-backed source; one timeframe at a time.
        row_count = len(frame)
        total_rows += row_count
        rows_by_timeframe[loaded.timeframe] = row_count
        samples[loaded.timeframe] = _json_safe_records(frame, sample_rows)
        try:
            outcome = validate_dataset(
                frame,
                symbol=config.symbol,
                timeframe=loaded.timeframe,
                source_name=loaded.source_file,
            )
        except DatasetValidationError as exc:
            validation_errors[loaded.timeframe] = str(exc)
            continue

        report = outcome.report
        validations[loaded.timeframe] = report.to_dict()
        total_memory += report.memory_bytes
        if report.timestamp_start:
            starts.append(report.timestamp_start)
        if report.timestamp_end:
            ends.append(report.timestamp_end)

    rows_by_split: dict[str, int | None] = {
        f"{configuration}/{split}": (int(value) if value is not None else None)
        for configuration, split_map in inventory.rows_by_configuration_split.items()
        for split, value in split_map.items()
    }
    return DatasetInspectionReport(
        created_at=datetime.now(timezone.utc).isoformat(),
        hub=inventory.to_dict(),
        total_rows=total_rows,
        rows_by_split=rows_by_split,
        rows_by_timeframe=rows_by_timeframe,
        detected_timeframes=tuple(rows_by_timeframe),
        samples_by_timeframe=samples,
        validations=validations,
        validation_errors=validation_errors,
        timestamp_start=min(starts) if starts else None,
        timestamp_end=max(ends) if ends else None,
        total_memory_bytes=total_memory,
    )


def render_markdown(report: DatasetInspectionReport) -> str:
    """Render a compact human-readable companion to the JSON report."""
    lines = [
        "# XAUUSD Dataset Inspection",
        "",
        f"- Created: `{report.created_at}`",
        f"- Dataset: `{report.hub['dataset_name']}`",
        f"- Requested revision: `{report.hub['requested_revision']}`",
        f"- Resolved revision: `{report.hub.get('resolved_revision')}`",
        f"- Total rows: `{report.total_rows:,}`",
        f"- Timestamp range: `{report.timestamp_start}` to `{report.timestamp_end}`",
        f"- In-memory size inspected: `{report.total_memory_bytes:,}` bytes",
        "",
        "## Hub structure",
        "",
        f"- Configurations: `{', '.join(report.hub['configurations'])}`",
        f"- Splits: `{report.hub['splits_by_configuration']}`",
        f"- Builder columns: `{report.hub['columns_by_configuration']}`",
        "",
        "## Rows by trusted timeframe source",
        "",
        "| Timeframe | Rows | Invalid rows | Exact duplicates | Conflicting keys | Gaps |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for timeframe, rows in report.rows_by_timeframe.items():
        validation = report.validations.get(timeframe, {})
        invalid = validation.get("invalid_rows", 0)
        continuity = validation.get("continuity", {})
        lines.append(
            f"| {timeframe} | {rows:,} | {invalid:,} | "
            f"{validation.get('exact_duplicate_rows', 0):,} | "
            f"{validation.get('conflicting_duplicate_keys', 0):,} | "
            f"{continuity.get('gaps', 0):,} |"
        )
    if report.validation_errors:
        lines.extend(["", "## Validation errors", ""])
        for timeframe, error in report.validation_errors.items():
            lines.append(f"- `{timeframe}`: {error}")
    lines.extend([
        "",
        "Gaps are reported, not filled. Weekend-like closures are counted separately",
        "from other gaps and still require review before downstream use.",
        "",
    ])
    return "\n".join(lines)


def write_reports(
    report: DatasetInspectionReport,
    report_root: Path,
) -> tuple[Path, Path]:
    """Atomically replace generated JSON and Markdown inspection reports."""
    report_root.mkdir(parents=True, exist_ok=True)
    json_path = report_root / "xauusd_validation.json"
    markdown_path = report_root / "xauusd_validation.md"
    json_temp = json_path.with_suffix(".json.tmp")
    markdown_temp = markdown_path.with_suffix(".md.tmp")
    json_temp.write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    markdown_temp.write_text(render_markdown(report), encoding="utf-8")
    json_temp.replace(json_path)
    markdown_temp.replace(markdown_path)
    return json_path, markdown_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect and validate Hugging Face XAUUSD data")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--sample-rows", type=int, default=5)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = load_config(args.config)
    inventory = inspect_hub_inventory(config)
    report = inspect_dataset(config, inventory, sample_rows=args.sample_rows)
    json_path, markdown_path = write_reports(report, config.report_root)
    print(json.dumps({
        "json_report": str(json_path),
        "markdown_report": str(markdown_path),
        "total_rows": report.total_rows,
        "rows_by_timeframe": report.rows_by_timeframe,
        "validation_errors": report.validation_errors,
    }, indent=2, sort_keys=True))
    return 1 if report.validation_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
