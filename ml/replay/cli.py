"""Command line entry point for offline historical candidate replay."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from ml.data.load_dataset import PROJECT_ROOT
from ml.data.validate_dataset import TIMEFRAME_SECONDS
from ml.replay.replay_engine import (
    ReplayResult,
    load_candles,
    load_replay_config,
    replay_candles,
    validate_source_manifest,
)
from ml.replay.replay_export import export_candidates
from ml.replay.replay_report import build_replay_report, write_replay_reports


DEFAULT_CONFIG = PROJECT_ROOT / "ml" / "configs" / "strategy_replay_v1.yaml"


def _effective_limit(args) -> int | None:
    if args.limit is not None:
        return args.limit
    if args.dry_run and args.start is None and args.end is None:
        return 500
    return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Replay production rules over cleaned candles")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--symbol")
    parser.add_argument("--timeframe")
    parser.add_argument("--strategy")
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    return parser


def run(args) -> dict:
    import pandas as pd

    config = load_replay_config(args.config)
    manifest = validate_source_manifest(config)
    symbol = (args.symbol or config.symbols[0]).upper()
    if symbol not in config.symbols:
        raise ValueError(f"Symbol is not configured: {symbol}")
    selected = [strategy for strategy in config.strategies
                if (not args.timeframe or strategy.timeframe == args.timeframe.upper())
                and (not args.strategy or strategy.name == args.strategy)]
    if not selected:
        raise ValueError("No configured strategy matches the CLI selection")
    if args.limit is not None and args.limit <= 0:
        raise ValueError("--limit must be positive")

    # An explicit date window is already bounded and must not be silently
    # truncated. Use the safety cap only for an otherwise unbounded dry run.
    effective_limit = _effective_limit(args)
    results: list[ReplayResult] = []
    for strategy in selected:
        frame = load_candles(
            config, symbol=symbol, timeframe=strategy.timeframe,
            start=args.start, end=args.end, limit=effective_limit,
        )
        htf_frame = None
        if strategy.confluence_timeframe:
            htf_start = None
            if args.start:
                htf_seconds = TIMEFRAME_SECONDS[strategy.confluence_timeframe]
                htf_start = pd.Timestamp(args.start) - pd.Timedelta(seconds=30 * htf_seconds)
            htf_frame = load_candles(
                config, symbol=symbol, timeframe=strategy.confluence_timeframe,
                start=htf_start, end=args.end,
                limit=(effective_limit if args.dry_run and not args.start else None),
            )
        results.append(replay_candles(
            frame, strategy=strategy, manifest=manifest,
            replay_config_version=config.version, htf_frame=htf_frame,
        ))
    candidates = tuple(candidate for result in results for candidate in result.candidates)
    output_files = ()
    output = None
    if not args.dry_run:
        output, output_files = export_candidates(
            candidates, output=config.candidates_root, source_manifest=manifest,
            config_version=config.version, compression=config.compression,
            overwrite=args.overwrite,
        )
    report = build_replay_report(results, output_files=output_files)
    reports = () if args.dry_run else write_replay_reports(report, config.reports_root)
    return {
        "dry_run": args.dry_run,
        "candidate_count": len(candidates),
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
