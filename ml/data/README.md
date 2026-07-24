# XAUUSD Dataset Ingestion and Validation

This package implements only historical-candle ingestion, inspection,
validation, deterministic cleaning, reporting, and partitioned Parquet export.
It contains no model training, feature engineering, labels, predictions, or
live trading integration.

## Source and timeframe provenance

The source is
[`ZombitX64/xauusd-gold-price-historical-data-2004-2025`](https://huggingface.co/datasets/ZombitX64/xauusd-gold-price-historical-data-2004-2025).
The Hub repository publishes separate JSONL files:

| Source file | Canonical timeframe |
|---|---|
| `XAU_1m_data.jsonl` | `M1` |
| `XAU_5m_data.jsonl` | `M5` |
| `XAU_15m_data.jsonl` | `M15` |
| `XAU_30m_data.jsonl` | `M30` |
| `XAU_1h_data.jsonl` | `H1` |
| `XAU_4h_data.jsonl` | `H4` |
| `XAU_1d_data.jsonl` | `D1` |
| `XAU_1w_data.jsonl` | `W1` |
| `XAU_1Month_data.jsonl` | `MN1` |

The default Hugging Face configuration combines files without guaranteeing a
per-row source filename. The pipeline does not infer timeframe from candle
spacing. It verifies configured filenames against Hub metadata, loads each file
independently, and applies only the trusted mapping in
`ml/configs/xauusd_dataset.yaml`.

The dataset card describes Date, Open, High, Low, Close, and Volume fields. The
inspection command records the actual builder and per-file schema; mismatches
fail safely.

## Installation and authentication

```bash
python -m pip install -r requirements.txt -r requirements-ml-data.txt
```

The dataset is public and normally requires no token. If authentication is
needed, set `HF_TOKEN` through the execution environment or secret manager.
Never put tokens in YAML, code, notebooks, or Git.

## Inspection and validation

```bash
python -m ml.data.inspect_dataset \
  --config ml/configs/xauusd_dataset.yaml
```

Generated reports:

```text
ml/data/reports/xauusd_validation.json
ml/data/reports/xauusd_validation.md
```

Reports cover Hub configurations, splits, counts, builder fields and types,
source-file metadata, samples, timestamp coverage, rows by timeframe, nulls,
exact duplicates, conflicting candle keys, ordering, OHLC violations,
non-positive prices, negative/zero volume, unexpected columns, memory use, and
continuity gaps.

Weekend-like gaps are classified separately but still reported. Monthly
continuity is reported without imposing a fixed number of seconds per month.
No interval is filled, interpolated, or fabricated.

## Cleaning and export

```bash
python -m ml.data.export_dataset \
  --config ml/configs/xauusd_dataset.yaml
```

Existing output causes a safe failure. Explicit replacement:

```bash
python -m ml.data.export_dataset \
  --config ml/configs/xauusd_dataset.yaml \
  --overwrite
```

The replacement is fully staged before promotion, with rollback if promotion
fails.

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

Parquet uses configured Zstandard compression. Hive partition fields are stored
in directory names and are not duplicated inside files.

## Canonical schema

```text
timestamp  # timezone-aware UTC
symbol     # XAUUSD
timeframe  # M1/M5/M15/M30/H1/H4/D1/W1/MN1
open       # float64
high       # float64
low        # float64
close      # float64
volume     # float64; never fabricated
source     # verified JSONL filename
```

`year` is derived only for partitioning.

## Validation and cleaning rules

- Require timestamp, OHLC, and volume source columns.
- Parse timestamps consistently as UTC.
- Verify source symbol/timeframe columns when present.
- Convert OHLC and volume to numeric values.
- Report invalid timestamps and non-finite numbers.
- Reject non-positive OHLC values.
- Enforce high/low consistency against open, close, and each other.
- Report negative and zero volume separately.
- Distinguish exact duplicate rows from conflicting candle keys.
- Remove exact duplicates only when configuration permits.
- Always fail on conflicting candles rather than choosing or averaging one.
- Remove fully empty rows and report the count.
- Sort by symbol, timeframe, and timestamp.
- Report gaps without resampling or creating candles.
- Fail on invalid market rows by default.

No legitimate historical value is rewritten beyond schema, type, and timezone
normalization. Invalid rows may be reported and excluded only when fail-safe
configuration is deliberately disabled.

## Manifest

`dataset_manifest.json` records requested and resolved Hub revisions, repository
commit when available, row counts, timeframes, timestamp range, canonical and
partition fields, report location, cleaning settings, file count, and a checksum
over relative Parquet filenames and contents.

## Generated-data policy

Downloads, caches, reports, and processed Parquet data are ignored by Git.
`ml/data/samples/` remains available for small, safe fixtures.

## Colab workflow

```python
!git clone <repository-url>
%cd qauntify_webV1
!pip install -r requirements-ml.txt

!python -m ml.data.inspect_dataset \
    --config ml/configs/xauusd_dataset.yaml

!python -m ml.data.export_dataset \
    --config ml/configs/xauusd_dataset.yaml \
    --overwrite
```

Colab is only an execution environment. Pipeline source and configuration stay
in this repository, and credentials belong in Colab Secrets.

## Known limitations

- The source card does not document timezone semantics. Parsing is consistent
  UTC, but the original timezone should be independently confirmed.
- Closure classification is heuristic and does not use a historical holiday
  calendar.
- The repository is about 875 MB and requires substantial disk, memory,
  bandwidth, and processing time.
- A successful download does not prove market-data correctness.
