"""Protected loader for frozen training_v3 classifier experiments."""
from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
import pyarrow.dataset as ds


def _ordered(frame):
    return frame.sort_values(["decision_timestamp", "candidate_id"], kind="mergesort").reset_index(drop=True)


def _read(dataset, *, filter_expression, columns, limit=None):
    scanner = dataset.scanner(columns=columns, filter=filter_expression, use_threads=False)
    table = scanner.head(limit) if limit else scanner.to_table()
    return _ordered(table.to_pandas())


def load_training_v3(root: Path, *, smoke: dict | None = None):
    manifest = json.loads((root / "training_manifest.json").read_text("utf-8"))
    if manifest.get("version") != "training_v3" or manifest.get("approval_status") != "approved_frozen":
        raise ValueError("Approved and frozen training_v3 is required")
    features = list(manifest["model_feature_columns"])
    targets = ["long_net_profitable", "short_net_profitable"]
    columns = ["candidate_id", "decision_timestamp", *features, *targets]
    dataset = ds.dataset(root / "dataset", format="parquet", partitioning="hive")
    # Deliberately no untouched-test branch in this loader.
    frames = {
        split: _read(dataset, filter_expression=ds.field("split") == split, columns=columns,
                     limit=smoke[f"{split}_rows"] if smoke else None)
        for split in ("train", "validation")
    }
    assignments = ds.dataset(root / "walk_forward_assignments", format="parquet", partitioning="hive")
    folds = {}
    for fold in range(1, 6):
        folds[fold] = {}
        for role in ("train", "validation"):
            count = smoke[f"{role}_rows"] if smoke else None
            table = assignments.scanner(
                columns=["candidate_id"],
                filter=(ds.field("fold") == fold) & (ds.field("role") == role),
                use_threads=False,
            ).head(count) if count else assignments.to_table(
                columns=["candidate_id"],
                filter=(ds.field("fold") == fold) & (ds.field("role") == role),
                use_threads=False,
            )
            ids = table.column("candidate_id")
            frame = dataset.to_table(columns=columns, filter=ds.field("candidate_id").isin(ids), use_threads=False).to_pandas()
            folds[fold][role] = _ordered(frame)
    return manifest, features, frames, folds
