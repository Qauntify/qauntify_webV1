# threshold_v2

`threshold_v2` consumes completed `tuning_v1` artifacts without retraining or
retuning. It cross-fits sigmoid and isotonic calibrators on five OOF validation
folds, searches calibrated thresholds from 0.50 through 0.56, evaluates optional
positive-regression and approved strategy/timeframe filters, and rejects every
policy that fails a hard economic safeguard.

The configuration intentionally leaves two assumptions unset. Audit them before
selection:

```bash
python -m ml.thresholding.cli audit --config ml/configs/threshold_v2.yaml
```

Validation-only selection requires explicit values:

```bash
python -m ml.thresholding.cli select \
  --config ml/configs/threshold_v2.yaml \
  --dataset-root /path/to/training_v1 \
  --tuning-root /path/to/tuning_v1 \
  --output-dir /path/to/threshold_v2 \
  --minimum-count-per-fold N \
  --trading-cost-r COST_IN_R
```

If and only if one policy is locked, the separately guarded command evaluates
the five frozen fold-model ensemble exactly once on the untouched test split:

```bash
python -m ml.thresholding.cli evaluate-test ... --confirm-untouched-test
```

Creation of `test_evaluation_state.json` is irreversible by policy. A started or
completed test evaluation cannot be repeated. None of these commands deploys a
model or changes live trading.

