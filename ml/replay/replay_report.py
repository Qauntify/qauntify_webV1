"""Machine- and human-readable candidate replay reporting."""
from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class ReplayReport:
    created_at: str
    candles_processed: int
    strategy_evaluations: int
    candidates_generated: int
    candidates_per_timeframe: dict[str, int]
    candidates_per_strategy: dict[str, int]
    candidates_per_direction: dict[str, int]
    candidate_frequency_by_year: dict[str, int]
    candidate_frequency_by_month: dict[str, int]
    first_candidate_timestamp: str | None
    last_candidate_timestamp: str | None
    invalid_candidate_count: int
    duplicate_candidate_count: int
    skipped_strategy_evaluations: int
    insufficient_history_occurrences: int
    runtime_warnings: tuple[str, ...]
    output_file_count: int
    output_size_bytes: int

    def to_dict(self) -> dict:
        return asdict(self)


def build_replay_report(results, *, output_files=(), runtime_warnings=()) -> ReplayReport:
    import pandas as pd

    candidates = [candidate for result in results for candidate in result.candidates]
    timestamps = [pd.Timestamp(candidate.candidate_timestamp) for candidate in candidates]
    return ReplayReport(
        created_at=datetime.now(timezone.utc).isoformat(),
        candles_processed=sum(result.stats.candles_processed for result in results),
        strategy_evaluations=sum(result.stats.strategy_evaluations for result in results),
        candidates_generated=len(candidates),
        candidates_per_timeframe=dict(sorted(Counter(c.timeframe for c in candidates).items())),
        candidates_per_strategy=dict(sorted(Counter(c.strategy_name for c in candidates).items())),
        candidates_per_direction=dict(sorted(Counter(c.direction for c in candidates).items())),
        candidate_frequency_by_year=dict(sorted(Counter(str(ts.year) for ts in timestamps).items())),
        candidate_frequency_by_month=dict(sorted(Counter(ts.strftime("%Y-%m") for ts in timestamps).items())),
        first_candidate_timestamp=min(timestamps).isoformat() if timestamps else None,
        last_candidate_timestamp=max(timestamps).isoformat() if timestamps else None,
        invalid_candidate_count=sum(result.stats.invalid_candidate_count for result in results),
        duplicate_candidate_count=sum(result.stats.duplicate_candidate_count for result in results),
        skipped_strategy_evaluations=sum(result.stats.skipped_strategy_evaluations for result in results),
        insufficient_history_occurrences=sum(
            result.stats.insufficient_history_occurrences for result in results
        ),
        runtime_warnings=tuple(runtime_warnings),
        output_file_count=len(output_files),
        output_size_bytes=sum(path.stat().st_size for path in output_files),
    )


def _markdown(report: ReplayReport) -> str:
    return "\n".join([
        "# Historical Candidate Replay Report",
        "",
        f"- Created: `{report.created_at}`",
        f"- Candles processed: `{report.candles_processed:,}`",
        f"- Strategy evaluations: `{report.strategy_evaluations:,}`",
        f"- Candidates generated: `{report.candidates_generated:,}`",
        f"- Candidate time range: `{report.first_candidate_timestamp}` to `{report.last_candidate_timestamp}`",
        f"- By timeframe: `{report.candidates_per_timeframe}`",
        f"- By strategy: `{report.candidates_per_strategy}`",
        f"- By direction: `{report.candidates_per_direction}`",
        f"- Invalid candidates: `{report.invalid_candidate_count}`",
        f"- Duplicate candidates: `{report.duplicate_candidate_count}`",
        f"- Insufficient-history evaluations: `{report.insufficient_history_occurrences}`",
        f"- Skipped evaluations: `{report.skipped_strategy_evaluations}`",
        f"- Output files: `{report.output_file_count}` ({report.output_size_bytes:,} bytes)",
        "",
        "## Frequency by year",
        "",
        f"`{report.candidate_frequency_by_year}`",
        "",
        "## Frequency by month",
        "",
        f"`{report.candidate_frequency_by_month}`",
        "",
        "This report describes rule frequency only. It contains no outcomes or quality assessment.",
        "",
    ])


def write_replay_reports(report: ReplayReport, report_root: Path) -> tuple[Path, Path]:
    report_root.mkdir(parents=True, exist_ok=True)
    json_path = report_root / "strategy_replay_v1.json"
    markdown_path = report_root / "strategy_replay_v1.md"
    json_tmp = json_path.with_suffix(".json.tmp")
    md_tmp = markdown_path.with_suffix(".md.tmp")
    json_tmp.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n", "utf-8")
    md_tmp.write_text(_markdown(report), "utf-8")
    json_tmp.replace(json_path)
    md_tmp.replace(markdown_path)
    return json_path, markdown_path
