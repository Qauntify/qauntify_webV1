from __future__ import annotations
import argparse,json
from pathlib import Path
from ml.training.v3_runner import run

def main():
    p=argparse.ArgumentParser();p.add_argument('--config',type=Path,default=Path('ml/configs/classifiers_v3.yaml'));p.add_argument('--experiment-dir',type=Path,required=True);p.add_argument('--dataset-root',type=Path);p.add_argument('--smoke',action='store_true');p.add_argument('--resume',action='store_true');a=p.parse_args()
    print(json.dumps(run(a.config.resolve(),a.experiment_dir.resolve(),smoke=a.smoke,resume=a.resume,dataset_root=a.dataset_root),indent=2))
if __name__=='__main__':main()
