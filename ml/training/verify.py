"""Colab preflight for the frozen dataset and feature contract."""
import argparse,json
from pathlib import Path
from ml.training.config import load_experiment_config
from ml.training.data import load_verified_training_data


def main(argv=None):
    parser=argparse.ArgumentParser();parser.add_argument("--config",type=Path,required=True);parser.add_argument("--dataset-root",type=Path,required=True);args=parser.parse_args(argv)
    config=load_experiment_config(args.config,dataset_root=args.dataset_root);data=load_verified_training_data(config,smoke=False)
    result={"status":"verified","training_dataset_id":data.manifest["training_dataset_id"],"checksum":data.manifest["checksum"],
        "feature_count":len(data.feature_columns),"main_rows":{key:len(value) for key,value in data.frames.items()},
        "walk_forward_rows":{f"fold_{fold:02d}":{key:len(value) for key,value in frames.items()} for fold,frames in data.walk_forward.items()},
        "future_fields_in_features":sorted(set(data.feature_columns)&set(data.manifest["future_derived_metadata_columns"]+data.manifest["target_columns"]))}
    print(json.dumps(result,indent=2,sort_keys=True));return 0


if __name__=="__main__":raise SystemExit(main())
