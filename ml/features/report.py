"""Feature dataset validation and summary reports."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from ml.features.schema import NUMERIC_FEATURES


def build_report(result, files=()):
    import pandas as pd
    frame = pd.DataFrame(result.features)
    summaries = {}
    for name in NUMERIC_FEATURES:
        series = pd.to_numeric(frame[name], errors="coerce")
        summaries[name] = {"non_null": int(series.notna().sum()), "null": int(series.isna().sum()),
                           "mean": float(series.mean()) if series.notna().any() else None,
                           "std": float(series.std(ddof=0)) if series.notna().any() else None,
                           "min": float(series.min()) if series.notna().any() else None,
                           "max": float(series.max()) if series.notna().any() else None}
    return {"created_at": datetime.now(timezone.utc).isoformat(), "candidates_processed": result.candidates_processed,
            "features_generated": len(result.features), "unique_candidate_ids": int(frame.candidate_id.nunique()),
            "by_strategy": frame.strategy_name.value_counts().sort_index().to_dict(),
            "by_timeframe": frame.timeframe.value_counts().sort_index().to_dict(),
            "column_count": len(frame.columns), "numeric_feature_statistics": summaries,
            "output_file_count": len(files), "output_size_bytes": sum(path.stat().st_size for path in files),
            "causality_boundary": "source_candle_close", "future_candles_used": False}


def write_reports(report, root):
    root.mkdir(parents=True, exist_ok=True)
    json_path = root / "feature_v1.json"; md_path = root / "feature_v1.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", "utf-8")
    md_path.write_text("\n".join(["# Historical Candidate Feature Report", "",
        f"- Candidates/features: `{report['candidates_processed']:,}` / `{report['features_generated']:,}`",
        f"- Unique candidate IDs: `{report['unique_candidate_ids']:,}`", f"- Strategies: `{report['by_strategy']}`",
        f"- Timeframes: `{report['by_timeframe']}`", f"- Feature columns (including identity/provenance): `{report['column_count']}`",
        f"- Output: `{report['output_file_count']}` files, `{report['output_size_bytes']:,}` bytes", "",
        "Every feature is calculated from history ending at the candidate's source-candle close. Candles at or after the candidate timestamp are not read by the row calculator.", "",
        "This dataset is separate from outcome labels and is not a training dataset.", ""]), "utf-8")
    return json_path, md_path

