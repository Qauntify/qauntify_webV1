"""Resume-aware tuning_v1 runner using only protected walk-forward folds."""
from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from ml.training.data import TARGET_BY_TASK, load_verified_training_data
from ml.training.evaluation import evaluate
from ml.training.runner import _catboost, _environment, _git_commit, _predict, _save_model, _sha256, _write_json
from ml.tuning.data import build_tuning_folds
from ml.tuning.selection import rank_trials, select_binary_threshold


def _identity(config, smoke):
    payload = json.dumps({"raw": config.raw, "dataset": str(config.dataset_root), "smoke": smoke, "commit": _git_commit()}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def _trial_id(index, trial):
    return f"trial_{index:02d}_{trial['name']}"


def _trial_config(config, trial, smoke):
    parameters = {**config.base.parameters, **{key: value for key, value in trial.items() if key != "name"}}
    smoke_values = {**config.base.smoke, **config.smoke}
    if smoke:
        parameters["iterations"] = int(config.smoke["iterations"])
    return replace(config.base, parameters=parameters, random_seed=config.random_seed, tasks=config.tasks, smoke=smoke_values)


def _run_fold(config, data, root, trial_id, task, fold, smoke):
    frames = data.walk_forward[fold]
    slug = f"{trial_id}__fold_{fold:02d}__{task}"
    model = _catboost(task, config, root, slug, frames["train"], frames["validation"], data.feature_columns, data.categorical_columns, smoke)
    _save_model(model, "catboost", root / "models" / trial_id / f"fold_{fold:02d}" / f"{task}.cbm")
    result = {}
    validation_output = None
    for role in ("train", "validation"):
        frame = frames[role]
        prediction, probabilities, classes = _predict(model, "catboost", task, frame, data.feature_columns)
        result[role] = evaluate(task, frame[TARGET_BY_TASK[task]].to_numpy(), prediction, probabilities, classes)
        if role == "validation":
            output = frame[["candidate_id", "candidate_timestamp", "target_binary_success", "target_outcome_class", "target_net_realized_r"]].copy()
            output["prediction"] = prediction
            if probabilities is not None:
                for index, label in enumerate(classes):
                    output[f"probability_{label}"] = probabilities[:, index]
                output["score"] = probabilities[:, list(classes).index(1)] if task == "binary" else probabilities.max(axis=1)
            else:
                output["score"] = prediction
            output["fold"] = fold
            path = root / "predictions" / trial_id / f"fold_{fold:02d}" / f"{task}_validation.parquet"
            path.parent.mkdir(parents=True, exist_ok=True)
            output.to_parquet(path, index=False, compression="zstd")
            validation_output = output
    return result, validation_output


def _write_selection(root, config, metrics, trials):
    import yaml

    ranked = rank_trials(metrics, config.selection, config.tasks)
    selected = {task: values[0]["trial_id"] for task, values in ranked.items()}
    trial_map = {_trial_id(index, trial): trial for index, trial in enumerate(trials, 1)}
    selected_dir = root / "selected_configs"
    selected_dir.mkdir(parents=True, exist_ok=True)
    for task, trial_id in selected.items():
        payload = {"policy_version": "tuning_v1", "task": task, "trial_id": trial_id,
                   "catboost": {**config.base.parameters, **{key: value for key, value in trial_map[trial_id].items() if key != "name"}},
                   "selection_policy": "walk-forward validation only; test excluded"}
        (selected_dir / f"{task}.yaml").write_text(yaml.safe_dump(payload, sort_keys=True), "utf-8")
    binary_frames = [pd.read_parquet(path) for path in sorted((root / "predictions" / selected["binary"]).rglob("binary_validation.parquet"))]
    threshold = select_binary_threshold(pd.concat(binary_frames, ignore_index=True), config.binary_thresholds)
    _write_json(root / "threshold_policy.json", {"version": "threshold_v1", "task": "binary", **threshold})
    report = {"version": "tuning_v1", "created_at": datetime.now(timezone.utc).isoformat(), "rankings": ranked,
              "selected_trials": selected, "binary_threshold": threshold,
              "test_usage": "not loaded, scored, ranked, or used for threshold selection",
              "deployment_status": "not_approved"}
    _write_json(root / "tuning_report.json", report)
    lines = ["# tuning_v1 selection report", "", "Selection uses five protected walk-forward validation folds only. The untouched test split is excluded.", ""]
    for task in config.tasks:
        winner = ranked[task][0]
        lines += [f"## {task.title()}", "", f"- Selected trial: `{winner['trial_id']}`", f"- Primary metric: `{winner['primary_metric']}`",
                  f"- Fold mean/std: `{winner['validation_mean']}` / `{winner['validation_std']}`", f"- Selection score: `{winner['selection_score']}`", ""]
    lines += ["## Binary threshold", "", f"- Selected threshold: `{threshold['selected']['threshold']}`",
              f"- Coverage: `{threshold['selected']['coverage']}`", f"- Mean net realized R: `{threshold['selected']['mean_net_realized_r']}`", "",
              "This is a locked offline selection artifact, not deployment approval.", ""]
    (root / "tuning_report.md").write_text("\n".join(lines), "utf-8")
    return report


def run_tuning(config, *, output_dir: Path, smoke=False, resume=False):
    root = output_dir.resolve()
    root.mkdir(parents=True, exist_ok=True)
    state_path = root / "run_state.json"
    identity = _identity(config, smoke)
    if state_path.exists():
        state = json.loads(state_path.read_text("utf-8"))
        if not resume:
            raise FileExistsError(f"Tuning output exists: {root}; use --resume")
        if state.get("config_identity") != identity:
            raise ValueError("Resume config does not match existing tuning experiment")
    else:
        state = {"config_identity": identity, "status": "running", "completed_jobs": [], "created_at": datetime.now(timezone.utc).isoformat()}
        _write_json(state_path, state)
    data = load_verified_training_data(_trial_config(config, config.trials[0], smoke), smoke=smoke)
    data = build_tuning_folds(data, config.dataset_root, config.tuning_folds)
    # Guardrail: tuning folds are rebuilt inside frozen train+validation only. data.frames['test'] is never passed to fit, metric, rank, or threshold functions.
    trials = config.trials[: config.smoke["trial_limit"]] if smoke else config.trials
    metrics_path = root / "walk_forward_metrics.json"
    metrics = json.loads(metrics_path.read_text("utf-8")) if metrics_path.exists() else {}
    for index, trial in enumerate(trials, 1):
        trial_id = _trial_id(index, trial)
        metrics.setdefault(trial_id, {task: {} for task in config.tasks})
        trial_config = _trial_config(config, trial, smoke)
        for task in config.tasks:
            for fold in range(1, 6):
                job = f"{trial_id}/{task}/fold_{fold:02d}"
                if job in state["completed_jobs"]:
                    continue
                fold_metrics, _ = _run_fold(trial_config, data, root, trial_id, task, fold, smoke)
                metrics[trial_id][task][str(fold)] = fold_metrics
                _write_json(metrics_path, metrics)
                state["completed_jobs"].append(job)
                state["last_completed_at"] = datetime.now(timezone.utc).isoformat()
                _write_json(state_path, state)
    report = _write_selection(root, config, metrics, trials)
    state.update({"status": "complete", "completed_at": datetime.now(timezone.utc).isoformat()})
    _write_json(state_path, state)
    _write_json(root / "environment.json", _environment())
    manifest = {"version": "tuning_v1", "status": "complete", "smoke": smoke, "training_dataset_id": data.manifest["training_dataset_id"],
                "training_dataset_checksum": data.manifest["checksum"], "trials": len(trials), "tasks": list(config.tasks),
                "folds": 5, "fold_policy": config.tuning_folds, "completed_jobs": len(state["completed_jobs"]), "expected_jobs": len(trials) * len(config.tasks) * 5,
                "selected_trials": report["selected_trials"], "test_rows_used": 0, "deployment_status": "not_approved"}
    _write_json(root / "tuning_manifest.json", manifest)
    files = tuple(sorted(path for path in root.rglob("*") if path.is_file() and path.name != "artifact_checksums.json"))
    _write_json(root / "artifact_checksums.json", {str(path.relative_to(root)).replace("\\", "/"): _sha256(path) for path in files})
    return manifest
