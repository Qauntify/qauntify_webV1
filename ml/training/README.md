# Baseline and CatBoost Training Framework

This offline framework consumes only the frozen `training_v1` dataset. The same
CLI, configs, loaders, target definitions, evaluation code, and artifact writer
are used locally and in Colab. It has no imports from or writes to live trading.

## Commands

```bash
python -m ml.training.cli --config ml/configs/baseline_v1.yaml --experiment-name baseline-run
python -m ml.training.cli --config ml/configs/catboost_v1.yaml --experiment-name catboost-run
```

Use `--smoke` only for bounded pipeline verification. Use an explicit persistent
directory and `--resume` after interruption:

```bash
python -m ml.training.cli --config ml/configs/catboost_v1.yaml \
  --dataset-root /content/drive/MyDrive/Quantify/training_v1 \
  --experiment-dir /content/drive/MyDrive/Quantify/experiments/catboost-v1 \
  --resume
```

CatBoost writes per-task snapshots into `snapshots/`. Completed tasks are marked
in `run_state.json` and skipped on resume. CatBoost documents `save_snapshot`
and `snapshot_file` as its interruption recovery mechanism:
https://catboost.ai/docs/en/features/snapshots

Each experiment saves native models, split predictions, metrics, the resolved
config, feature/target contract, run state, experiment manifest, and SHA-256
checksums. Baselines use prior class probability or the median regression target.
CatBoost uses validation-based early stopping and saves native `.cbm` models.

Full runs execute 18 jobs per family: binary, multiclass, and regression on the
main chronological split plus those three tasks on each of the five protected
walk-forward folds. Main test predictions are generated only after fitting and
are never used for model or threshold selection. The runner also saves grouped
performance, confusion matrices, calibration tables, score buckets, regression
predicted-versus-realized diagnostics, feature importance, bounded SHAP
summaries, environment details, logs, snapshots, and artifact checksums.

After both families complete, generate the comparison report with:

```bash
python -m ml.training.compare \
  --baseline-dir /path/to/baseline_v1 \
  --catboost-dir /path/to/catboost_v1 \
  --output-dir /path/to/comparison
```

No feature selection, hyperparameter tuning, deployment, or live integration is
performed by this framework.
