"""CLI for the offline training_v3 dataset build."""
from __future__ import annotations
import argparse
from pathlib import Path
from ml.training_dataset.v3_builder import export


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("ml/configs/training_dataset_v3.yaml"))
    parser.add_argument("--output", type=Path, default=Path("ml/data/datasets/training_v3"))
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    manifest = export(args.config.resolve(), args.output.resolve(), args.overwrite)
    print(f"training_v3 rows={manifest['rows']} eligible={manifest['training_eligible_rows']} checksum={manifest['dataset_checksum']}")


if __name__ == "__main__":
    main()
