# Quantify ML Research and Training

> **NOT WIRED INTO THE LIVE ENGINE.** Nothing in this directory, in
> `signals/ml/`, or in `model/` affects a delivered signal. Every signal a user
> receives comes from the deterministic detectors in `signals/strategies/` plus
> the SEA-LION confirmation gate. `tests/core/test_ml_not_wired.py` enforces
> this and will fail if the live path ever imports the ML tree.
>
> This is research scaffolding, and it is not ready to gate real trades: the
> progress report below is explicit that leakage-safety of the training data
> has not been verified end to end. When connecting a model, put it behind a
> sampling flag and shadow-record its verdicts first — measure, then enforce.

This directory is the source of truth for offline data work, research, model
training, calibration, and evaluation. Training code stays in the main Quantify
repository even when it executes on Colab, Kaggle, CI, or another machine.

The overall architecture is documented in
[`docs/model-training-and-signal-engine-integration.md`](../docs/model-training-and-signal-engine-integration.md).

## Responsibilities

```text
ml/
├── data/        # Ingestion, inspection, validation, cleaning, and export
├── notebooks/   # Exploration and thin Colab/Kaggle entry points
├── training/    # Future offline training orchestration
├── features/    # Re-export of the canonical live-safe feature builder
├── labels/      # Future versioned candidate outcome labels
├── evaluation/  # Future walk-forward evaluation and calibration
└── configs/     # Version-controlled pipeline configuration
```

Critical logic must live in importable `.py` modules. Notebooks should import
repository modules rather than contain the only implementation. Training must
never run inside a Next.js request or the live signal-engine loop.

## XAUUSD dataset stage

The implemented offline-only stage targets
[`ZombitX64/xauusd-gold-price-historical-data-2004-2025`](https://huggingface.co/datasets/ZombitX64/xauusd-gold-price-historical-data-2004-2025).
It stops after validated, cleaned, partitioned Parquet export. It does not
create indicators, labels, candidates, outcomes, models, or predictions.

Full instructions and validation policy:
[`ml/data/README.md`](data/README.md).

The next offline-only stage records historical rule candidates by reusing the
production strategy router. See [`ml/replay/README.md`](replay/README.md).

```bash
python -m pip install -r requirements.txt -r requirements-ml-data.txt
python -m ml.data.inspect_dataset --config ml/configs/xauusd_dataset.yaml
python -m ml.data.export_dataset --config ml/configs/xauusd_dataset.yaml
```

## Environment setup

Production dependencies remain in `requirements.txt`. Offline data dependencies
are isolated in `requirements-ml-data.txt`; the larger research/training stack
is in `requirements-ml.txt`.

```bash
python -m venv .venv-ml
python -m pip install -r requirements.txt
python -m pip install -r requirements-ml.txt
```

Never paste Supabase, Hugging Face, Telegram, or market credentials into a
notebook. Use the compute environment's secret manager.

## Shared feature boundary

The canonical candidate feature calculation is
`signals.ml.features.build_candidate_features`. Future offline training must
import that implementation through `ml.features` to prevent training-serving
skew. The current dataset pipeline does not call it because feature engineering
is out of scope.

## Artifact lifecycle

```text
artifacts/
├── candidates/   # Imported bundles awaiting verification and shadow tests
├── active/       # Explicitly approved production bundles only
├── previous/     # Rollback-ready previously approved bundles
└── legacy_lstm/  # Preserved historical XAUUSD LSTMs and scalers
```

An eventual candidate bundle is expected to contain the model, calibrator,
feature schema/order, categorical features, label mapping, thresholds, metrics,
dataset manifest, training configuration, dependency lock, and checksum. No
fake trained artifacts are included in the current scaffold.

The signal engine must only load explicitly approved artifacts and must never
deserialize an artifact received from an untrusted source.

## Legacy LSTM models

Historical XAUUSD `.keras` files are preserved in `artifacts/legacy_lstm/`;
their scalers are in `artifacts/legacy_lstm/scalers/`. The legacy notebook lives
at `ml/notebooks/XAUUSD_prediction_colab_run_m1.ipynb`. These files are not used
or changed by the dataset pipeline.
