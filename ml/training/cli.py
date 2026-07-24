"""Shared local/Colab entry point for baseline and CatBoost experiments."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from ml.training.config import load_experiment_config
from ml.training.runner import run_experiment


def main(argv=None):
    parser=argparse.ArgumentParser(description="Train frozen training_v1 baselines or CatBoost models")
    parser.add_argument("--config",type=Path,required=True); parser.add_argument("--dataset-root",type=Path)
    parser.add_argument("--artifacts-root",type=Path); parser.add_argument("--experiment-dir",type=Path)
    parser.add_argument("--experiment-name"); parser.add_argument("--resume",action="store_true"); parser.add_argument("--smoke",action="store_true")
    args=parser.parse_args(argv)
    config=load_experiment_config(args.config,dataset_root=args.dataset_root,artifacts_root=args.artifacts_root)
    if args.experiment_dir: experiment=args.experiment_dir
    else:
        name=args.experiment_name or f"{config.version}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
        experiment=config.artifacts_root/name
    manifest=run_experiment(config,experiment_dir=experiment,smoke=args.smoke,resume=args.resume)
    print(json.dumps({"experiment_dir":str(experiment.resolve()),"manifest":manifest},indent=2,sort_keys=True)); return 0


if __name__=="__main__": raise SystemExit(main())
