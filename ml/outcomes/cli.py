"""CLI for offline candidate outcome resolution."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from ml.outcomes.config import DEFAULT_CONFIG_PATH, load_outcome_config
from ml.outcomes.export import export_outcomes
from ml.outcomes.pipeline import resolve_outcomes
from ml.outcomes.report import build_report, write_reports


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Resolve historical candidate outcomes")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--strategy")
    parser.add_argument("--timeframe")
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    return parser


def run(args) -> dict:
    if args.limit is not None and args.limit <= 0:
        raise ValueError("--limit must be positive")
    config = load_outcome_config(args.config)
    result = resolve_outcomes(
        config,
        strategy=args.strategy,
        timeframe=args.timeframe.upper() if args.timeframe else None,
        start=args.start,
        end=args.end,
        limit=args.limit,
    )
    output = None
    files = ()
    reports = ()
    if not args.dry_run:
        output, files = export_outcomes(result, config=config, overwrite=args.overwrite)
    report = build_report(result, output_files=files)
    if not args.dry_run:
        reports = write_reports(report, config.reports_root)
    return {
        "dry_run": args.dry_run,
        "output": str(output) if output else None,
        "reports": [str(path) for path in reports],
        "stats": report.to_dict(),
    }


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    print(json.dumps(run(args), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

