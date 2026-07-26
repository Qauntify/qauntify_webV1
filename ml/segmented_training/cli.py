"""Shared local/Colab entry point for training_v2_segmented_temporal."""
import argparse,json
from pathlib import Path
from ml.segmented_training.config import load_segmented_config
from ml.segmented_training.runner import run_segmented_training


def main(argv=None):
    parser=argparse.ArgumentParser(); parser.add_argument("--config",type=Path,required=True); parser.add_argument("--dataset-root",type=Path)
    parser.add_argument("--experiment-dir",type=Path,required=True); parser.add_argument("--resume",action="store_true"); parser.add_argument("--smoke",action="store_true")
    args=parser.parse_args(argv); config=load_segmented_config(args.config,dataset_root=args.dataset_root,artifacts_root=args.experiment_dir)
    result=run_segmented_training(config,experiment_dir=args.experiment_dir,smoke=args.smoke,resume=args.resume); print(json.dumps(result,indent=2,sort_keys=True)); return 0


if __name__=="__main__": raise SystemExit(main())
