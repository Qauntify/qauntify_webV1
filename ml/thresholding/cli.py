"""CLI for threshold_v2 assumption audit, selection, and exactly-once test."""
from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path

from ml.thresholding.config import load_threshold_config
from ml.thresholding.policy import select_and_lock_policy
from ml.thresholding.test_evaluation import evaluate_untouched_test_once


def _config(args):
    config = load_threshold_config(args.config, dataset_root=args.dataset_root, tuning_root=args.tuning_root, output_root=args.output_dir)
    if getattr(args, "minimum_count_per_fold", None) is not None:
        config = replace(config, minimum_count_per_fold=args.minimum_count_per_fold)
    if getattr(args, "trading_cost_r", None) is not None:
        config = replace(config, trading_cost_r=args.trading_cost_r)
    return config


def main(argv=None):
    parser = argparse.ArgumentParser(description="Validation-only threshold_v2 policy workflow")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("audit", "select", "evaluate-test"):
        item = sub.add_parser(name)
        item.add_argument("--config", type=Path, required=True)
        item.add_argument("--dataset-root", type=Path)
        item.add_argument("--tuning-root", type=Path)
        item.add_argument("--output-dir", type=Path)
        item.add_argument("--minimum-count-per-fold", type=int)
        item.add_argument("--trading-cost-r", type=float)
        if name == "evaluate-test":
            item.add_argument("--confirm-untouched-test", action="store_true")
    args = parser.parse_args(argv)
    config = _config(args)
    if args.command == "audit":
        result = {"version": config.version, "missing_assumptions": list(config.missing_assumptions), "test_evaluation_allowed": False,
                  "reason": "Set assumptions, complete validation selection, and lock one policy first"}
    elif args.command == "select":
        result = select_and_lock_policy(config, output_dir=args.output_dir)
    else:
        result = evaluate_untouched_test_once(config, output_dir=args.output_dir, confirmed=args.confirm_untouched_test)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

