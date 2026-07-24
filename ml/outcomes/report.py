"""Outcome resolution summary reports."""
from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class OutcomeReport:
    created_at: str
    candidates_processed: int
    outcomes_generated: int
    outcomes_by_class: dict[str, int]
    outcomes_by_strategy: dict[str, int]
    outcomes_by_timeframe: dict[str, int]
    outcomes_by_direction: dict[str, int]
    entry_triggered: int
    tp1_hits: int
    tp2_hits: int
    tp3_hits: int
    stop_hits: int
    expiries: int
    right_censored: int
    ambiguous_parent_candles: int
    lower_timeframe_resolutions: int
    conservative_fallbacks: int
    mean_holding_seconds: float | None
    mean_mfe_r: float | None
    mean_mae_r: float | None
    mean_gross_realized_r: float | None
    mean_net_realized_r: float | None
    output_file_count: int
    output_size_bytes: int
    runtime_warnings: tuple[str, ...]

    def to_dict(self) -> dict:
        return asdict(self)


def build_report(result, *, output_files=(), runtime_warnings=()) -> OutcomeReport:
    outcomes = result.outcomes
    resolved = [outcome for outcome in outcomes if outcome.gross_realized_r is not None]

    def mean(values):
        values = list(values)
        return sum(values) / len(values) if values else None

    return OutcomeReport(
        created_at=datetime.now(timezone.utc).isoformat(),
        candidates_processed=result.candidates_processed,
        outcomes_generated=len(outcomes),
        outcomes_by_class=dict(sorted(Counter(o.outcome_class for o in outcomes).items())),
        outcomes_by_strategy=dict(sorted(Counter(o.strategy_name for o in outcomes).items())),
        outcomes_by_timeframe=dict(sorted(Counter(o.timeframe for o in outcomes).items())),
        outcomes_by_direction=dict(sorted(Counter(o.direction for o in outcomes).items())),
        entry_triggered=sum(o.entry_triggered for o in outcomes),
        tp1_hits=sum(o.tp1_hit for o in outcomes),
        tp2_hits=sum(o.tp2_hit for o in outcomes),
        tp3_hits=sum(o.tp3_hit for o in outcomes),
        stop_hits=sum(o.sl_hit for o in outcomes),
        expiries=sum(o.expired for o in outcomes),
        right_censored=sum(o.right_censored for o in outcomes),
        ambiguous_parent_candles=sum(o.ambiguous_parent_candles for o in outcomes),
        lower_timeframe_resolutions=sum(o.lower_timeframe_resolutions for o in outcomes),
        conservative_fallbacks=sum(o.conservative_fallbacks for o in outcomes),
        mean_holding_seconds=mean(o.holding_seconds for o in outcomes),
        mean_mfe_r=mean(o.mfe_r for o in outcomes),
        mean_mae_r=mean(o.mae_r for o in outcomes),
        mean_gross_realized_r=mean(o.gross_realized_r for o in resolved),
        mean_net_realized_r=mean(o.net_realized_r for o in resolved),
        output_file_count=len(output_files),
        output_size_bytes=sum(path.stat().st_size for path in output_files),
        runtime_warnings=tuple(runtime_warnings),
    )


def _markdown(report: OutcomeReport) -> str:
    return "\n".join([
        "# Historical Candidate Outcome Report",
        "",
        f"- Created: `{report.created_at}`",
        f"- Candidates processed: `{report.candidates_processed:,}`",
        f"- Outcomes generated: `{report.outcomes_generated:,}`",
        f"- Classes: `{report.outcomes_by_class}`",
        f"- Strategies: `{report.outcomes_by_strategy}`",
        f"- Timeframes: `{report.outcomes_by_timeframe}`",
        f"- Directions: `{report.outcomes_by_direction}`",
        f"- Entry triggered: `{report.entry_triggered:,}`",
        f"- TP1 / TP2 / TP3: `{report.tp1_hits:,}` / `{report.tp2_hits:,}` / `{report.tp3_hits:,}`",
        f"- Stops / expiries / censored: `{report.stop_hits:,}` / `{report.expiries:,}` / `{report.right_censored:,}`",
        f"- Ambiguous parent candles: `{report.ambiguous_parent_candles:,}`",
        f"- Lower-timeframe resolutions: `{report.lower_timeframe_resolutions:,}`",
        f"- Conservative fallbacks: `{report.conservative_fallbacks:,}`",
        f"- Mean holding seconds: `{report.mean_holding_seconds}`",
        f"- Mean MFE / MAE: `{report.mean_mfe_r}` / `{report.mean_mae_r}`",
        f"- Mean gross / net R: `{report.mean_gross_realized_r}` / `{report.mean_net_realized_r}`",
        f"- Output: `{report.output_file_count}` files, `{report.output_size_bytes:,}` bytes",
        "",
        "This report describes deterministic outcome_v1 resolution. It is not a training or profitability report.",
        "",
    ])


def write_reports(report: OutcomeReport, root: Path) -> tuple[Path, Path]:
    root.mkdir(parents=True, exist_ok=True)
    json_path = root / "outcome_v1.json"
    markdown_path = root / "outcome_v1.md"
    json_tmp = json_path.with_suffix(".json.tmp")
    markdown_tmp = markdown_path.with_suffix(".md.tmp")
    json_tmp.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n", "utf-8")
    markdown_tmp.write_text(_markdown(report), "utf-8")
    json_tmp.replace(json_path)
    markdown_tmp.replace(markdown_path)
    return json_path, markdown_path

