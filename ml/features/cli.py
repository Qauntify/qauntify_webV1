"""CLI for offline feature_v1 generation."""
import argparse
import json
from pathlib import Path

from ml.features.config import DEFAULT_CONFIG_PATH, load_feature_config
from ml.features.export import export_features
from ml.features.pipeline import generate_features
from ml.features.report import build_report, write_reports


def main(argv=None):
    parser = argparse.ArgumentParser(description="Generate causal candidate features")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--strategy"); parser.add_argument("--timeframe")
    parser.add_argument("--start"); parser.add_argument("--end"); parser.add_argument("--limit", type=int)
    parser.add_argument("--dry-run", action="store_true"); parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    if args.limit is not None and args.limit <= 0: raise ValueError("--limit must be positive")
    config = load_feature_config(args.config)
    result = generate_features(config, strategy=args.strategy, timeframe=args.timeframe.upper() if args.timeframe else None,
                               start=args.start, end=args.end, limit=args.limit)
    output = None; files = (); reports = ()
    if not args.dry_run:
        output, files, _ = export_features(result, config, args.overwrite)
    report = build_report(result, files)
    if not args.dry_run: reports = write_reports(report, config.reports_root)
    print(json.dumps({"dry_run": args.dry_run, "output": str(output) if output else None,
                      "reports": [str(path) for path in reports], "summary": report}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__": raise SystemExit(main())

