# tuning_v1

`tuning_v1` performs a deliberately bounded CatBoost search on the frozen
`training_v1` dataset. Because the frozen replay folds extend into the main test
period, tuning creates five nested expanding folds strictly within the frozen
train+validation pool. These folds retain the 14-day embargo and purge training
labels whose resolution reaches validation. Chronological test candidates are
never passed to model fitting, trial ranking, or binary threshold selection.

The ranking score rewards the oriented primary metric and penalizes fold
variability and train/validation overfitting. Binary thresholds are selected
from concatenated out-of-time validation predictions using realized R, coverage,
and fold variability. Selected configs and `threshold_v1` are offline artifacts;
they are not deployment approval and do not change live trading.

Bounded local verification:

```bash
python -m ml.tuning.cli --config ml/configs/tuning_v1.yaml \
  --output-dir artifacts/tuning/smoke-v1 --smoke
```

Full resumable Colab run:

```bash
python -m ml.tuning.cli --config ml/configs/tuning_v1.yaml \
  --dataset-root /content/drive/MyDrive/Quantify/training_v1_full_001/datasets/datasets/training_v1 \
  --output-dir /content/drive/MyDrive/Quantify/training_v1_full_001/tuning/tuning_v1 \
  --resume
```
