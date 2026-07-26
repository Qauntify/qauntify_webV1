# training_v2_segmented_temporal

This experiment trains independent `ict_fvg/M5` and `sr_zone/M15` binary and regression CatBoost models. Each of the five frozen outer walk-forward folds contains three nested, expanding, embargoed calibration folds built only from the outer training window. The calibrator never sees the outer validation window or a later fold.

Thresholds are selected separately per segment from calibrated outer-validation predictions over `0.40..0.60` in `0.005` increments. A policy is rejected unless it passes the fixed coverage, per-fold volume, fold consistency, cost, fold-concentration, and year-concentration safeguards. The untouched test split is neither scored nor used for selection.

Run a bounded smoke check:

```bash
python -m ml.segmented_training.cli --config ml/configs/training_v2_segmented_temporal.yaml --dataset-root /path/to/training_v1 --experiment-dir /path/to/output --smoke --resume
```

Run the full resumable experiment by omitting `--smoke`. Outputs include per-fold models, calibrators, OOF predictions, policy tables, cost sensitivity, reports, manifests, environment details, and checksums. This experiment does not deploy or modify live trading behavior.
