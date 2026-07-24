"""Local and Colab entry point for tuning_v1."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from ml.tuning.config import load_tuning_config
from ml.tuning.runner import run_tuning


def main(argv=None):
    parser = argparse.ArgumentParser(description="Tune CatBoost using validation and walk-forward folds only")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--dataset-root", type=Path)
    parser.add_argument("--artifacts-root", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--experiment-name")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args(argv)
    config = load_tuning_config(args.config, dataset_root=args.dataset_root, artifacts_root=args.artifacts_root)
    if args.output_dir:
        output = args.output_dir
    else:
        name = args.experiment_name or f"tuning-v1-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
        output = config.artifacts_root / name
    manifest = run_tuning(config, output_dir=output, smoke=args.smoke, resume=args.resume)
    print(json.dumps({"output_dir": str(output.resolve()), "manifest": manifest}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

