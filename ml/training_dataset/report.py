import json
from datetime import datetime, timezone


def build_report(result, files=()):
    frame = result.dataset
    eligible = frame[frame.supervised_eligible]
    fold_counts = result.walk_forward_assignments[result.walk_forward_assignments.supervised_eligible].groupby(["fold", "role"]).size().unstack(fill_value=0).to_dict("index")
    return {"created_at": datetime.now(timezone.utc).isoformat(), "rows": len(frame), "unique_candidate_ids": int(frame.candidate_id.nunique()),
            "supervised_eligible": int(frame.supervised_eligible.sum()), "right_censored": int(frame.right_censored.sum()),
            "split_counts_all": frame.split.value_counts().sort_index().to_dict(),
            "split_counts_eligible": eligible.split.value_counts().sort_index().to_dict(),
            "target_class_counts": eligible.target_outcome_class.value_counts().sort_index().to_dict(),
            "binary_counts": {str(key): int(value) for key, value in eligible.target_binary_success.value_counts().sort_index().items()},
            "net_r_mean": float(eligible.target_net_realized_r.mean()), "net_r_std": float(eligible.target_net_realized_r.std(ddof=0)),
            "walk_forward_eligible_counts": fold_counts, "split_policy": result.split_policy,
            "output_file_count": len(files), "output_size_bytes": sum(path.stat().st_size for path in files)}


def write_reports(report, root):
    root.mkdir(parents=True, exist_ok=True); jp=root/"training_v1.json"; mp=root/"training_v1.md"
    jp.write_text(json.dumps(report, indent=2, sort_keys=True)+"\n", "utf-8")
    mp.write_text("\n".join(["# Training Dataset Builder Report", "", f"- Joined rows / unique IDs: `{report['rows']:,}` / `{report['unique_candidate_ids']:,}`",
        f"- Supervised eligible / right-censored: `{report['supervised_eligible']:,}` / `{report['right_censored']:,}`",
        f"- All split assignments: `{report['split_counts_all']}`", f"- Eligible split assignments: `{report['split_counts_eligible']}`",
        f"- Eligible multiclass targets: `{report['target_class_counts']}`", f"- Binary targets: `{report['binary_counts']}`",
        f"- Walk-forward folds: `{report['walk_forward_eligible_counts']}`", "",
        "Binary success is net_realized_r > 0. Zero and negative R are failures. Right-censored rows retain coverage but have null regression/binary targets and are supervised-ineligible.", "",
        "Splits use candidate timestamp order, a 14-day pre-boundary embargo, and label-window purging. Training labels must resolve before validation starts; validation labels must resolve before test starts.", "",
        "No feature selection, model fitting, or hyperparameter tuning is performed.", ""]), "utf-8")
    return jp,mp
