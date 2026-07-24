# ML Training Section Progress Report

**Project:** Quantify / XAUUSD signal engine  
**Report date:** 2026-07-24  
**Current phase:** Data preparation and historical candidate generation infrastructure

## Executive summary

The project is not training a new model yet. Work completed so far establishes
the safe, reproducible foundation required before training:

1. Existing legacy XAUUSD models were preserved and separated from future
   training artifacts.
2. A versioned Hugging Face dataset ingestion, inspection, validation,
   cleaning, and Parquet export pipeline was implemented.
3. The complete historical XAUUSD dataset was downloaded and successfully
   validated.
4. Clean candles were exported into partitioned Parquet with a dataset
   manifest and checksum.
5. A historical deterministic-strategy replay pipeline was implemented to
   produce future training candidates without using future candles.
6. No candidate outcomes, training features, labels, new models, deployment,
   or live trading changes have been implemented yet.

The next correct stage is to execute and verify the historical strategy replay,
then design outcome labels and a leakage-safe feature dataset. Model training
should begin only after those datasets are reviewed.

## 1. Repository and ML structure

The ML-related repository structure now separates data preparation, replay,
future research, and production artifacts:

```text
qauntify_webV1/
|-- artifacts/
|   |-- active/
|   |-- candidates/
|   |-- experiments/
|   |-- legacy_lstm/
|   `-- previous/
|-- ml/
|   |-- configs/
|   |   |-- strategy_replay_v1.yaml
|   |   `-- xauusd_dataset.yaml
|   |-- data/
|   |   |-- raw/
|   |   |-- processed/
|   |   |-- reports/
|   |   |-- clean_dataset.py
|   |   |-- export_dataset.py
|   |   |-- inspect_dataset.py
|   |   |-- load_dataset.py
|   |   `-- validate_dataset.py
|   |-- replay/
|   |   |-- candidate_builder.py
|   |   |-- candidate_schema.py
|   |   |-- replay_engine.py
|   |   |-- replay_export.py
|   |   |-- replay_report.py
|   |   |-- strategy_adapter.py
|   |   `-- cli.py
|   |-- evaluation/
|   |-- features/
|   |-- labels/
|   |-- notebooks/
|   `-- training/
|-- signals/
|   |-- ml/
|   `-- strategies/
`-- tests/ml/
    |-- data/
    `-- replay/
```

The `training`, `labels`, and `evaluation` directories remain placeholders for
later stages. This is intentional: training has not been started prematurely.

## 2. Existing model artifact handling

Historical XAUUSD LSTM models and scalers were preserved under
`artifacts/legacy_lstm/`. The old prediction notebook was moved under
`ml/notebooks/`.

These legacy artifacts are not regenerated, retrained, or automatically loaded
by the new data and replay pipelines. This keeps historical experiments
available while preventing them from being confused with a future approved
production model.

The artifact lifecycle now distinguishes:

- `artifacts/experiments/`: offline experiment outputs.
- `artifacts/candidates/`: model bundles awaiting validation.
- `artifacts/active/`: explicitly approved production bundles.
- `artifacts/previous/`: rollback-ready prior production bundles.
- `artifacts/legacy_lstm/`: preserved historical models.

## 3. Dataset pipeline implemented

The dataset stage uses the Hugging Face dataset:

```text
ZombitX64/xauusd-gold-price-historical-data-2004-2025
```

The pipeline verifies repository files and loads each timeframe file
independently. This is important because the combined Hugging Face split does
not preserve a trustworthy timeframe value on every row.

Implemented dataset operations include:

- Hub configuration, split, schema, source-file, and revision inspection.
- Explicit source-filename-to-timeframe mapping.
- Timestamp parsing as timezone-aware UTC.
- Canonical column normalization.
- Numeric and non-finite value validation.
- OHLC relationship validation.
- Non-positive price checks.
- Negative and zero-volume reporting.
- Exact duplicate and conflicting candle-key detection.
- Chronological ordering and continuity-gap reporting.
- Safe deterministic cleaning.
- Partitioned Parquet export.
- JSON and Markdown validation reports.
- Dataset manifest, source revision, file count, and checksum generation.
- Rollback-safe replacement requiring an explicit overwrite option.

No missing candles are fabricated, interpolated, or backfilled.

## 4. Dataset download and validation results

The complete dataset was downloaded successfully without requiring an
`HF_TOKEN`. Hugging Face issued only an unauthenticated rate-limit warning.

### Dataset identity

```text
Resolved Hugging Face revision:
ff6469dc91bad67f3ceea3f1b5e3df1224f26ba7

Dataset ID:
sha256:145409150cb6459a70f93b4bac0ae24d053123487d5beb47e9848bab5ee262f6

Cleaned dataset checksum:
18b0f11556181ae34bd2302b8c0a24804f08557055cb0c437710860c51262b55
```

### Validation summary

| Check | Result |
|---|---:|
| Total rows | 8,887,001 |
| Validation errors | 0 |
| Invalid rows | 0 |
| Exact duplicate rows | 0 |
| Conflicting candle keys | 0 |
| Parquet files | 198 |
| Historical start | 2004-06-01 00:00 UTC |
| Historical end | 2025-10-01 05:29 UTC |
| Raw cache size | approximately 537 MB |
| Cleaned Parquet size | approximately 151 MB |

### Rows by timeframe

| Timeframe | Rows |
|---|---:|
| M1 | 6,600,530 |
| M5 | 1,402,971 |
| M15 | 480,717 |
| M30 | 242,152 |
| H1 | 121,823 |
| H4 | 32,074 |
| D1 | 5,383 |
| W1 | 1,096 |
| MN1 | 255 |

### Export layout

```text
ml/data/processed/cleaned_candles/
|-- dataset_manifest.json
`-- symbol=XAUUSD/
    |-- timeframe=M1/year=YYYY/*.parquet
    |-- timeframe=M5/year=YYYY/*.parquet
    |-- timeframe=M15/year=YYYY/*.parquet
    |-- timeframe=M30/year=YYYY/*.parquet
    |-- timeframe=H1/year=YYYY/*.parquet
    |-- timeframe=H4/year=YYYY/*.parquet
    |-- timeframe=D1/year=YYYY/*.parquet
    |-- timeframe=W1/year=YYYY/*.parquet
    `-- timeframe=MN1/year=YYYY/*.parquet
```

Generated raw data, reports, and processed files are ignored by Git.

## 5. Canonical candle schema

The cleaned candle dataset uses:

```text
timestamp   timezone-aware UTC timestamp
symbol      XAUUSD
timeframe   M1/M5/M15/M30/H1/H4/D1/W1/MN1
open        float64
high        float64
low         float64
close       float64
volume      float64
source      verified Hugging Face JSONL filename
```

`year` is derived only for storage partitioning.

## 6. Historical strategy replay implemented

A historical candidate replay pipeline has been implemented but has not yet
been executed against the full cleaned dataset.

The replay calls the existing production strategy router instead of creating a
second implementation of strategy rules. The configured default streams are:

| Primary timeframe | Strategy | Confluence |
|---|---|---|
| M5 | `ict_fvg` | closed M15 trend |
| M15 | `sr_zone` | none |
| H1 | `ema_cross` | closed H4 trend |

Other available strategies such as `ict_smc` and `ce_lwma` were not enabled
automatically because they are selectable rather than default active streams.

The replay stage:

- Reads the cleaned dataset manifest before processing.
- Uses timeframe-specific Parquet partition reads.
- Supports date, symbol, timeframe, strategy, and row-limit filters.
- Processes candles chronologically.
- Supplies detectors only the candle history available at that time.
- Uses closed candles only.
- Aligns higher-timeframe data using already-closed HTF candles.
- Produces deterministic candidate IDs.
- Validates entry, stop-loss, TP geometry, direction, and timestamps.
- Rejects duplicate or conflicting candidate IDs.
- Rejects future-derived and outcome fields.
- Exports candidates into partitioned Parquet with a candidate manifest.
- Requires explicit overwrite before replacing existing output.

## 7. Candidate schema prepared for future training

The versioned `candidate_v1` schema contains:

```text
candidate_id
candidate_timestamp
source_candle_timestamp
symbol
timeframe
strategy_name
strategy_version
direction
entry_price
stop_loss
take_profit_1
take_profit_2
take_profit_3
risk_distance
risk_reward_tp1
risk_reward_tp2
risk_reward_tp3
signal_reason
candidate_status
dataset_id
dataset_checksum
replay_config_version
source_commit
created_at
schema_version
```

This schema deliberately contains no result, win/loss status, future return,
exit price, realized R, or training label.

## 8. Future-leakage protections

The current replay design protects the future training dataset at its source:

- Strategy detectors receive only candles through the current closed candle.
- Production indicator functions are causal and sliced at the current index.
- No centered rolling window is used.
- No negative shift is used.
- No indicator values are backfilled from future rows.
- Higher-timeframe trends use only HTF candles already closed at decision time.
- Candidate decision timestamps are derived from the current source candle.
- Tests compare historical prefixes before and after future candles are
  appended.
- Production-parity tests compare replay adapter output with the live strategy
  router for the same fixed history.

## 9. Testing and validation performed

### Successfully executed

- Hugging Face download: successful.
- Dataset inspection: successful.
- Full dataset validation: successful.
- Partitioned Parquet export: successful.
- Dataset manifest verification: successful.
- Exported file-count verification: 198 manifest files and 198 actual files.
- Existing web tests: 61 passed.
- Existing web lint: zero errors and one unrelated pre-existing warning.
- Git whitespace validation: passed.

### Replay tests implemented

Synthetic replay tests cover:

- Empty and insufficient datasets.
- No-signal periods.
- Valid long and short candidates.
- Deterministic IDs.
- Invalid TP/SL geometry.
- Exact and conflicting candidate IDs.
- Chronological ordering.
- Duplicate candle keys.
- Selected date ranges and partition pruning.
- Multiple strategies on one candle.
- Partitioned export and manifest creation.
- Safe overwrite behavior.
- Appended-future-candle leakage checks.
- Causal indicator prefix stability.
- Production strategy-router parity.

The Python runtime and dependencies were installed locally after the initial
implementation. The replay suite should be executed before running the full
historical replay.

## 10. Work intentionally not implemented

The following work has not been performed:

- Candidate outcome resolution.
- Win/loss or multi-class labels.
- Maximum favorable/adverse excursion labels.
- Training feature generation.
- Feature selection.
- Train/validation/test temporal splits.
- Walk-forward cross-validation.
- Model training or hyperparameter tuning.
- Probability calibration.
- Model comparison or approval thresholds.
- Production model bundle creation.
- Shadow inference.
- ML filtering of live signals.
- Live trading behavior changes.

No claim should currently be made that a new model has been trained or is ready
for production.

## 11. Current risks and limitations

1. The source dataset timestamp timezone convention is not independently
   documented by the provider. The pipeline parses timestamps consistently as
   UTC, but the original market timezone should still be confirmed.
2. Gap classification uses a weekend-style heuristic rather than a complete
   historical XAUUSD holiday/session calendar.
3. Historical replay has not yet produced real candidate counts.
4. Candidate outcomes and label policy require careful design to avoid
   ambiguous same-candle TP/SL ordering and future leakage.
5. Existing legacy LSTM artifacts do not provide evidence that they match the
   new canonical dataset, replay candidates, or future feature schema.

## 12. Recommended next steps

Proceed in this order:

1. Run all Python dataset and replay unit tests.
2. Run a bounded M5 `ict_fvg` dry replay over a short historical period.
3. Review candidate frequency, timestamps, direction, entry, stop, and targets.
4. Run production-parity checks on selected real historical windows.
5. Run the complete configured candidate replay only after the bounded run is
   accepted.
6. Freeze the resulting candidate manifest and checksum.
7. Design a separate, versioned candidate-outcome policy.
8. Implement labels without changing the candidate records.
9. Build causal features at each candidate timestamp.
10. Create temporal train/validation/test and walk-forward splits.
11. Compare simple baseline models before testing complex sequence models.
12. Package a model only after reproducibility, calibration, and leakage checks
    pass.

Example bounded replay command:

```powershell
python -m ml.replay.cli `
  --config ml/configs/strategy_replay_v1.yaml `
  --strategy ict_fvg `
  --timeframe M5 `
  --start 2024-01-01 `
  --end 2024-01-07 `
  --dry-run
```

## Conclusion

The ML section now has a validated historical market-data foundation and a
production-aligned candidate replay design. The dataset is downloaded,
validated, versioned, and exportable. The project is ready for replay
verification, but it is not yet ready for outcome labeling or model training.

