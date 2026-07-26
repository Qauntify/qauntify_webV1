"""CLI for guarded segmented post-training selection."""
import argparse,json
from pathlib import Path
from ml.segmented_training.config import load_segmented_config
from ml.segmented_training.policy import select_segmented_policy


def main(argv=None):
    parser=argparse.ArgumentParser(); parser.add_argument("--config",type=Path,required=True); parser.add_argument("--dataset-root",type=Path); parser.add_argument("--experiment-dir",type=Path,required=True)
    args=parser.parse_args(argv); config=load_segmented_config(args.config,dataset_root=args.dataset_root,artifacts_root=args.experiment_dir)
    result=select_segmented_policy(config,experiment_dir=args.experiment_dir); print(json.dumps(result,indent=2,sort_keys=True)); return 0


if __name__=="__main__": raise SystemExit(main())
