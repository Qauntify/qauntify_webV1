# Indicator Model v3 Progress Tracker

## Current status

```text
Project: XAUUSD indicator-based directional model
Decision timeframe: M5
Context timeframe: M15
Dataset period: 2016-01-04 through 2026-01-30
Current stage: classifier_v3 full Colab execution setup verified
Labels: label_v3.1 approved/frozen — 701,154 rows; 700,996 supervised eligible
Features: feature_v3 approved/frozen — 701,154 rows; 700,532 eligible
Training dataset: training_v3 approved/frozen — 701,154 rows; 700,388 jointly eligible
Classifier framework: smoke and job-level resume passed; full Colab run not started
Models: Not trained
Untouched test: Locked
Deployment/live integration: Not authorised
```

## Objective

At the close of each completed XAUUSD M5 candle, independently estimate the
probability that a hypothetical LONG or SHORT entered at the next M5 open will
finish with positive net realised R.

The deterministic policy will eventually return `LONG`, `SHORT`, or
`NO_TRADE`. The LLM is outside training and may only provide a future
explanation layer.

## Completed work

### 1. Previous model track paused

The previous strategy-candidate and segmented-model work is no longer the active
research direction. Existing historical reports and artifacts were not reused
to define the new labels, features, or policy.

### 2. v3 architecture written

The plan was rewritten for:

- XAUUSD only;
- M5 decisions and entries;
- completed M15 context;
- no M1, H1, or H4 dependency;
- next-M5-open entry;
- 48-M5-bar/four-hour outcome horizon;
- conservative SL-first handling when TP and SL touch in the same M5 candle;
- independent long and short profitability targets;
- deterministic `NO_TRADE` conflict handling;
- chronological splits, purging, embargo, and locked test access;
- no live-trading changes.

Primary specification:

```text
docs/indicator_trading_model_training_plan_v3.md
```

### 3. Replacement datasets prepared

The supplied full-history M5 and M15 CSV files were filtered using a
2016-01-01 calendar cutoff. The previous five-year filtered copies and the old
M5/M15 Hugging Face cache entries were removed. Other timeframe caches and the
original Downloads files were not modified.

| Timeframe | Rows | First candle | Last candle | SHA-256 |
|---|---:|---|---|---|
| M5 | 701,154 | 2016-01-04 01:05 | 2026-01-30 23:55 | `5432E9D54B77D4B7B5201482B7403A0663208BA9B66BEE22F52689A2ABC6D1E0` |
| M15 | 234,859 | 2016-01-04 01:00 | 2026-01-30 23:45 | `02330690AA21D31035BDD684D03327E8BFC30C68F36DAB4B135EF3E3A543EBAC` |

Stored files:

```text
ml/data/raw/xauusd_m5_2016_2026.csv
ml/data/raw/xauusd_m15_2016_2026.csv
```

### 4. Data audit completed

Results:

- invalid OHLC rows: 0;
- duplicate timestamps: 0;
- chronology violations: 0;
- zero-volume rows: 0;
- complete M15 intervals comparable with three M5 bars: 231,470;
- exact OHLCV matches for those intervals: 231,470 (100%);
- M15 intervals with incomplete component-M5 coverage: 3,389.

Two material source gaps were detected and preserved:

1. after 2025-09-12 23:45 through approximately 2025-10-15 07:45/07:55;
2. after 2026-01-13 14:15 through approximately 2026-01-22 18:45/18:50.

Any label window crossing either gap must be marked `INVALID` and excluded from
supervised training.

Known source limitations:

- timestamp timezone is undeclared;
- OHLC bid/ask/mid convention is undeclared;
- historical spread is unavailable;
- volume type is undeclared.

These limitations do not block price-based label research using the approved
all-in cost proxy. They do block timezone-dependent session features until the
timezone is resolved.

Audit artifacts:

```text
ml/data/reports/data_audit_v3.json
ml/data/reports/data_audit_v3.md
ml/data/manifests/data_v3_manifest.json
ml/data/reports/xauusd_m5_m15_10year_replacement.json
```

### 5. Milestone 1 configuration contracts implemented

Created:

```text
ml/configs/experiments/xauusd_m5_directional_v1.yaml
ml/configs/labels/label_v3.yaml
ml/configs/costs/xauusd_cost_v3.yaml
ml/configs/splits/xauusd_m5_split_v3.yaml
ml/configs/policies/policy_safeguards_v3.yaml
ml/config_schema_v3.py
tests/ml/test_config_schema_v3.py
```

Locked label assumptions:

```text
Entry: next M5 open
ATR: M5 ATR(14), frozen at decision time
TP: 1.5 ATR
SL: 1.0 ATR
Horizon: 48 M5 bars
Same-M5 TP/SL: SL first
M1 resolution: disabled
Binary targets: directional net realised R > 0
```

Cost scenarios:

```text
Base:   0.02 R — must pass
Higher: 0.03 R — must pass
Stress: 0.05 R — report, not a hard pass
```

Safeguards:

```text
Minimum coverage: 5%
Minimum accepted candidates per fold: 100
Minimum total accepted candidates: 500
Minimum positive folds: 4 of 5
Maximum execution-constrained drawdown: 25 R
Maximum single-fold positive-profit share: 40%
Maximum single-year positive-profit share: 50%
Maximum locked policies: 1
```

## Proposed temporal split

The revised ten-year split is approved.

| Partition | Start | End exclusive |
|---|---|---|
| Train | 2016-01-01 | 2024-01-01 |
| Validation | 2024-01-01 | 2025-01-01 |
| Untouched test | 2025-01-01 | 2026-01-31 |

Five expanding validation folds cover six-month periods from July 2022 through
December 2024. All training windows begin in 2016. Split boundaries use
outcome-exit timestamp purging and a 240-minute embargo.

## Validation and testing status

The YAML contracts and their cross-contract relationships were parsed and
validated with the available local JavaScript YAML runtime. A strict Python
validator and focused pytest tests were added, but the current local environment
does not have a Python runtime installed, so those pytest tests have not been
executed locally.

No full test suite was run.

## label_v3 outcome dataset

The directional outcome resolver is implemented using production-compatible
Wilder ATR(14), next-M5-open entry, 1.5 ATR TP, 1.0 ATR SL, and a 48-bar
horizon. Long and short paths are resolved independently. Same-candle TP/SL
ties are conservatively assigned to SL.

Full results:

```text
Rows: 701,154
Unique candidate IDs: 701,154
Supervised eligible: 700,996
ATR warm-up invalid: 14
Material-gap invalid: 96
Right censored: 48
Dataset checksum: C6009EAA5C0AEFFC72B626617CE5A4F5EE036CDBE69FD744B30E71DB8E532673
```

Directional target summaries after the 0.02 R base cost:

```text
Long positive rate:  39.9490%
Short positive rate: 40.0068%
Long mean net R:     -0.022561 R
Short mean net R:    -0.021079 R
```

Ambiguity:

```text
Long ambiguity rows: 2,761
Short ambiguity rows: 2,840
Either direction: 4,682
Both directions: 919
```

The directional ambiguity counts overlap when one candidate is ambiguous for
both directions. MFE and MAE include the full terminal-candle OHLC range because
intrabar ordering is unavailable.

Validation completed:

- 11 focused tests passed;
- bounded 10,000-row verification passed;
- exact one-to-one candidate coverage passed;
- two complete full runs produced identical manifests and partition checksums;
- temporary smoke and verification datasets were removed after comparison.

Artifacts:

```text
ml/outcomes/label_v3.py
ml/outcomes/label_v3_cli.py
tests/ml/outcomes/test_label_v3.py
ml/data/processed/labels_v3/
ml/data/reports/label_v3.json
ml/data/reports/label_v3.md
```

## Timestamp correction

`label_v3` stored candle-open time under the decision timestamp field. It has
been retired from downstream use. `label_v3.1` preserves the source open time,
uses open time plus five minutes as the completed-candle decision time, and
derives candidate IDs from that corrected timestamp. All economic outcomes,
target rates, ambiguity counts and eligibility counts are unchanged.

```text
Active label version: label_v3_1
Dataset checksum: 12487C516D860E56A1AAC346391B853B30C6B58055DA8494A7F9AF14D22D00E5
Focused tests: 12 passed
```

## Feature specification

The exact `feature_v3` formulas, M5/M15 closed-candle alignment, warm-up policy,
gap handling, exclusions and leakage tests are defined in:

```text
docs/feature_v3_specification.md
ml/configs/feature_v3.yaml
```

Session/calendar and volume-derived features are excluded because their source
semantics are not verified.

## Current gate

The policy safeguard and revised split configurations are approved. The split
configuration is marked:

```text
approved
```

The `training_v3` dataset and protected split artifacts are complete and
pending review/freeze. Untouched-test evaluation, deployment and live
integration remain separately blocked.

## Next step

Review and freeze `training_v3`. After that gate, implement and locally smoke-
test the baseline and untuned directional classifier framework. Do not run full
training or inspect untouched-test performance without separate authorization.
