from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from ml.config_schema_v3 import load_and_validate_v3_configs
from ml.outcomes.label_v3 import (
    LabelV3Settings, build_validation_report, export_labels, file_sha256,
    load_m5_csv, resolve_labels, write_validation_reports,
)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Generate offline label_v3 outcomes")
    parser.add_argument("--config-root", type=Path, default=Path("ml/configs"))
    parser.add_argument("--output", type=Path, default=Path("ml/data/processed/labels_v3_1"))
    parser.add_argument("--limit", type=int)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    bundle = load_and_validate_v3_configs(args.config_root)
    if not bundle.ready_for_label_implementation:
        raise RuntimeError("v3 configuration approvals are incomplete")
    source = Path(bundle.experiment["input"]["M5"])
    candles = load_m5_csv(source, limit=args.limit)
    gap_values = bundle.split.get("known_source_gaps", [])
    gaps = tuple((pd.Timestamp(item["start_exclusive"]), pd.Timestamp(item["end_inclusive"])) for item in gap_values)
    costs = bundle.cost["scenarios"]
    settings = LabelV3Settings(costs_r=tuple(float(costs[key]["total_round_trip_cost_r"]) for key in ("base", "higher", "stress")))
    labels = resolve_labels(candles, settings, material_gaps=gaps)
    manifest = export_labels(labels, args.output.resolve(), overwrite=args.overwrite, contract_metadata={
        "config_checksums": dict(bundle.checksums),
        "label_v3_1_config_sha256": file_sha256(Path("ml/configs/labels/label_v3_1.yaml")),
        "source_m5": str(source),
        "source_m5_sha256": "5432E9D54B77D4B7B5201482B7403A0663208BA9B66BEE22F52689A2ABC6D1E0",
        "entry": "next_m5_open",
        "atr": "wilder_14_frozen_at_decision",
        "target_atr": settings.target_atr,
        "stop_atr": settings.stop_atr,
        "horizon_bars": settings.horizon_bars,
        "same_candle_policy": "stop_first_conservative",
        "timestamp_correction": "decision_timestamp_is_source_bar_open_plus_5_minutes",
        "costs_r": list(settings.costs_r),
    })
    if args.limit is None:
        write_validation_reports(build_validation_report(labels, manifest), Path("ml/data/reports").resolve())
    print(json.dumps(manifest, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
