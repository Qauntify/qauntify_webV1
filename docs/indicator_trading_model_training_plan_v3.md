# Indicator Trading Model Training Plan — Version 3

## Document status

```text
Specification version: v3
Primary experiment: xauusd_m5_directional_v1
Label contract: label_v3
Feature contract: feature_v3
Policy contract: policy_v3
Implementation status: Draft — configuration approval required
Test-set status: Locked until the complete policy is frozen
Live-trading status: No changes authorised
```

This document replaces `indicator_trading_model_training_plan_v2.md` for the
new indicator-based model. It defines a supervised research pipeline for one
instrument and one decision timeframe. It does not authorise deployment,
live-signal integration, position sizing, or changes to production strategies.

The first implementation must stop after each approval gate described below.

## 1. Objective

At the close of each completed XAUUSD M5 candle, independently estimate:

- the probability that a hypothetical LONG entered at the next executable M5
  open finishes with positive net realised R; and
- the probability that a hypothetical SHORT entered at the same open finishes
  with positive net realised R.

The deterministic policy converts these estimates into:

```text
LONG
SHORT
NO_TRADE
```

`NO_TRADE` is a policy result, not a learned class. The LLM is not part of
training, labelling, calibration, threshold selection, or risk control.

## 2. Locked experiment scope

```yaml
experiment_id: xauusd_m5_directional_v1
instrument: XAUUSD
eligible_start_source_time: 2016-01-01T00:00:00
eligible_end_source_time: 2026-01-30T23:59:59
decision_timeframe: M5
context_timeframes: [M15]
decision_timestamp: current_m5_close
entry_timestamp: next_m5_open
candidate_frequency_bars: 1
allow_overlapping_label_candidates: true
use_m1_data: false
random_seed: 42
```

The first experiment must not mix decision timeframes or instruments.

## 3. Non-negotiable rules

1. Use chronological splits only.
2. Use only information available at the decision timestamp for features.
3. Use only fully closed M5 and M15 candles.
4. Calculate long and short outcomes independently.
5. Preserve gross outcomes and net outcomes separately.
6. Do not convert right-censored observations into failures or expiries.
7. Resolve every same-M5-candle TP/SL ambiguity conservatively as SL first. M1
   data must not be used by this experiment.
8. Fit imputation, scaling, models, and calibration inside the applicable
   training fold only.
9. Use validation and out-of-fold predictions for every selection decision.
10. Keep the final test set inaccessible until the full policy is frozen.
11. Reject a policy that fails any hard safeguard.
12. Version and checksum every input, configuration, dataset, and artifact.
13. Reuse the repository's existing `ml/` architecture.
14. Do not modify live trading behaviour.

## 4. Repository placement

Use existing modules where their contracts remain compatible. Add versioned
modules or configuration under `ml/` only when required by this specification.

```text
docs/indicator_trading_model_training_plan_v3.md
ml/configs/experiments/xauusd_m5_directional_v1.yaml
ml/configs/labels/label_v3.yaml
ml/configs/costs/xauusd_cost_v3.yaml
ml/configs/splits/xauusd_m5_split_v3.yaml
ml/configs/policies/policy_safeguards_v3.yaml
ml/outcomes/
ml/features/
ml/training_dataset/
ml/training/
ml/calibration/
ml/thresholding/
ml/evaluation/
ml/inference/
ml/data/reports/
```

Do not create a competing top-level `src/` modelling architecture.

## 5. Source-data contract

Required candle fields:

```text
timestamp, open, high, low, close, volume, timeframe
```

The source manifest must state:

- symbol and data provider;
- timestamp timezone;
- whether OHLC represents bid, ask, midpoint, or an unknown convention;
- whether volume is exchange volume, broker tick volume, or unknown;
- spread availability and units;
- date range and row counts by timeframe;
- missing and duplicate candle counts;
- SHA-256 checksums.

Validation must check chronology, duplicate keys, OHLC consistency, positive
prices, incomplete candles, timezone consistency, expected closures, unexpected
gaps, and M5/M15 continuity. OHLC candles must not be forward-filled.

The existing cleaned XAUUSD dataset may be reused only after its manifest and
checksums pass this contract. Only M5 decisions from 2016-01-01 through
2026-01-30 and their completed M15 context are eligible. Older and other-
timeframe source data must be retained unchanged but excluded by configuration.
Reusing the data does not permit modifying the frozen v1 datasets or manifests.

## 6. `label_v3` contract

### 6.1 Decision, entry, and horizon

For a completed decision candle indexed `t`:

```text
decision time       = close timestamp of M5[t]
entry time          = open timestamp of M5[t+1]
entry price         = open price of M5[t+1]
ATR                 = ATR(14) computed through M5[t]
outcome scan bars   = M5[t+1] through M5[t+48], inclusive
expiry time         = close timestamp of M5[t+48]
expiry price        = close price of M5[t+48]
```

The entry candle is the first outcome candle. ATR is frozen at the decision
timestamp. A row is not eligible when `t+1` is missing or non-executable.
The maximum nominal holding period is `48 × M5 = 4 hours`.

### 6.2 Barriers

```text
long TP  = entry + 1.5 × ATR[t]
long SL  = entry - 1.0 × ATR[t]
short TP = entry - 1.5 × ATR[t]
short SL = entry + 1.0 × ATR[t]
```

Long and short paths are resolved independently.

### 6.3 Outcome states

Each direction must retain one terminal state:

```text
TP
SL
EXPIRED
AMBIGUOUS_CONSERVATIVE_SL
RIGHT_CENSORED
INVALID
```

The ambiguity state must also retain which economic terminal result—TP or
SL—was assigned.

### 6.4 Intrabar ambiguity

When an M5 candle touches both barriers, resolve SL first. Do not load or inspect
M1 data. Record `ambiguity_detected = true` and
`conservative_fallback = true`. The terminal state is
`AMBIGUOUS_CONSERVATIVE_SL`, and the economic terminal result is `SL`.

For the entry candle, scanning begins at its open. No price movement before the
entry timestamp may be used.

### 6.5 Expiry

If neither barrier is reached through `M5[t+48]`, exit at that candle's close.

```text
long gross R  = (expiry close - entry) / (ATR[t] × 1.0)
short gross R = (entry - expiry close) / (ATR[t] × 1.0)
```

Preserve the `EXPIRED` state even when its realised R is positive.

### 6.6 Right-censoring and invalid rows

If any part of the required 48-bar future window is unavailable because the
dataset ends, mark both directional outcomes `RIGHT_CENSORED`, retain the row in
the outcome dataset, and exclude it from supervised training.

Unexpected internal gaps follow the source-data policy and must be recorded as
`INVALID` unless a later approved configuration explicitly defines another
resolution. Invalid rows must never be silently dropped.

### 6.7 Classification and regression targets

The classification target is economic profitability, not barrier identity:

```text
long_net_profitable  = 1 when long_net_realised_r  > 0, else 0
short_net_profitable = 1 when short_net_realised_r > 0, else 0
```

It is null for right-censored and invalid rows. The model outputs must be named:

```text
p_long_net_profitable
p_short_net_profitable
```

Barrier results remain metadata for diagnostics. Optional regression targets
are:

```text
long_net_realised_r
short_net_realised_r
```

CatBoost regressors are a gated second stage, not required to begin classifier
training. They may be added only after classifier baselines and label quality
are approved.

### 6.8 Required outcome fields

The separate outcome dataset, keyed one-to-one by `candidate_id`, must include:

```text
candidate_id
decision_timestamp
entry_timestamp
entry_price
atr_at_decision
long_tp_price, long_sl_price
short_tp_price, short_sl_price
long_result, short_result
long_economic_terminal, short_economic_terminal
long_net_profitable, short_net_profitable
long_gross_r, short_gross_r
long_net_realised_r, short_net_realised_r
long_mfe_r, long_mae_r
short_mfe_r, short_mae_r
long_exit_price, short_exit_price
long_exit_timestamp, short_exit_timestamp
long_holding_bars, short_holding_bars
ambiguity_detected
conservative_fallback
right_censored
invalid_reason
```

Candidate records must not be modified.

## 7. Transaction-cost contract

Costs must be expressed consistently in R and preserved by component. Until a
broker-specific bid/ask convention is verified, the research scenarios are:

```yaml
cost_version: xauusd_cost_v3
price_convention: must_be_confirmed_from_source_manifest
scenarios:
  base:
    total_round_trip_cost_r: 0.02
  higher:
    total_round_trip_cost_r: 0.03
  stress:
    total_round_trip_cost_r: 0.05
primary_scenario: base
```

These are all-in research cost proxies. Do not separately subtract spread,
commission, or slippage on top of the proxy. If historical spread and verified
broker costs later replace the proxy, create a new cost version; do not rewrite
`xauusd_cost_v3`.

```text
net realised R = gross realised R - total round-trip cost R
```

Policy selection must pass the base and higher scenarios. Stress results must
be reported and may not be hidden, but stress positivity is not a hard v3
requirement.

## 8. Feature contract

Features for decision candle `t` may use only:

- M5 data at or before `M5[t]`; and
- the most recent M15 candle whose close is not later than the decision time.

Use backward as-of joins with an explicit closed-candle test. UTC is the storage
timezone. Session features must use timezone-aware London and New York daylight
saving rules rather than fixed UTC offsets.

The detailed `feature_v3` contract must define exact formulas, parameters,
lookbacks, minimum periods, missing-value behaviour, and feature names before
feature implementation. Permitted groups are:

- trend: SMA, EMA, slopes, alignment, ATR-normalised distances;
- momentum: RSI, MACD, rate of change;
- volatility: ATR, Bollinger width, realised volatility;
- trend strength: ADX and directional indicators;
- candles: body, wick, range, return, and break features;
- deterministic BBMA states;
- session and calendar context;
- closed M15 context.

Vague visual descriptions are prohibited. Warm-up rows are explicitly
ineligible until every required feature is valid. Do not impute warm-up history.

## 9. Overlap and executable-policy evaluation

Every valid M5 candle is an independent research decision point, so label rows
may overlap. Raw candidate count must not be described as independent trade
count.

Report two distinct evaluations:

1. **Independent-candidate evaluation** — evaluates predictive discrimination
   and per-candidate economics.
2. **Execution-constrained evaluation** — approximates an executable stream.

The initial execution constraint is:

```yaml
maximum_open_positions: 1
signals_while_position_open: ignore
opposing_positions_allowed: false
same_timestamp_long_short_conflict: NO_TRADE
position_size_risk_units: 1.0
```

Signals are processed chronologically. Once accepted, a position remains open
until its labelled exit timestamp. Later signals during that interval are not
executed. Portfolio total R, profit factor, drawdown, and consecutive-loss
metrics must use the execution-constrained stream. Independent-candidate totals
must be labelled clearly and must not be presented as portfolio performance.

## 10. Training dataset

One row represents one decision timestamp. Join features and outcomes exactly
one-to-one by `candidate_id`. Signal-time features are model inputs; future
outcome fields are targets or metadata only.

Required integrity checks:

- unique candidate IDs;
- exact join coverage;
- no forbidden outcome columns in the feature matrix;
- no right-censored or invalid targets in supervised rows;
- deterministic row ordering and output checksums;
- class and outcome distributions by time period.

## 11. Chronological splits and test governance

Split dates must be written to `xauusd_m5_split_v3.yaml` and approved before
any model fitting. No executable configuration may contain null split dates.

Each decision at `t` can depend on prices through `t+48`. Split protection must
compare timestamps, not merely row offsets:

- purge any training row whose outcome interval reaches the validation start;
- use a minimum nominal purge span of 48 M5 bars (4 hours), while the actual
  row-level check uses each outcome exit timestamp;
- embargo 48 M5 bars (4 hours) after a boundary when forming subsequent
  training windows;
- account for the next-bar entry offset explicitly;
- apply the same rule to all five expanding-window walk-forward folds.

The final test range must be frozen before feature ablation, model selection,
calibration, or threshold selection. Test data must be blocked by default in the
CLI and require an approval artifact plus a frozen-policy manifest and matching
checksums. Every access attempt must be logged. Test results may be generated
exactly once for `policy_v3` and cannot be used to revise that policy.

## 12. Models and staged development

### Stage A — baselines

Train separately for long and short:

- prevalence/majority baseline;
- logistic regression;
- shallow decision tree;
- random forest baseline.

### Stage B — initial CatBoost classifiers

Train one untuned CatBoost classifier per direction using the same feature and
split contracts. Use early stopping inside each fold.

### Stage C — feature-group ablation

Evaluate groups and removals using protected validation folds only. Fit all
preprocessing within folds. Prefer stable, simpler feature sets.

### Stage D — optional regressors

Only after classifier review and explicit approval, train simple regression
baselines and then optional CatBoost regressors for directional net R.

### Stage E — tuning

Only after feature groups are frozen may Optuna tune approved CatBoost
parameters. Do not jointly tune labels, features, costs, model parameters,
calibration, and policy thresholds.

No stage authorises local full training unless separately requested. Local runs
must be bounded smoke tests; full runs may use the existing shared Colab/CLI
framework.

## 13. Out-of-fold prediction and calibration

Every selection input must come from protected validation or out-of-fold
predictions. Save candidate ID, timestamp, fold, direction, target, raw
probability, calibrated probability, and—when approved—predicted net R.

Compare no calibration, Platt scaling, and isotonic regression. Calibration must
be cross-fitted: a row cannot be used both to fit its calibrator and to evaluate
that calibrator. Select using Brier score, log loss, expected calibration error,
reliability curves, and stability across folds. Never fit or select calibration
on the test split.

## 14. Deterministic decision policy

Initial classifier-only gates are:

```text
long_pass  = calibrated p_long_net_profitable  >= long_threshold
short_pass = calibrated p_short_net_profitable >= short_threshold
```

If approved regressors are later added, a new policy configuration may also
require predicted directional net R to exceed a validation-selected minimum.

Conflict handling is fixed for `policy_v3`:

```text
long passes only  -> LONG
short passes only -> SHORT
both pass         -> NO_TRADE
neither passes    -> NO_TRADE
```

No LLM may override this policy.

## 15. Policy selection safeguards

The following previously approved minimum safeguards apply:

```yaml
total_folds: 5
minimum_positive_folds: 4
minimum_coverage: 0.05
minimum_accepted_candidates_per_fold: 100
reject_zero_trade_folds: true
require_positive_mean_net_r_base_cost: true
require_positive_total_net_r_base_cost: true
require_positive_total_net_r_higher_cost: true
reject_if_any_hard_safeguard_fails: true
```

Before threshold search, the policy configuration must additionally receive
approved numeric values for:

```text
minimum total accepted candidates
maximum execution-constrained drawdown R
maximum single-fold profit contribution
maximum single-year profit contribution
```

Until those four values and split dates are approved, policy optimisation and
test evaluation are blocked. Safeguards must not be weakened to force a policy
to pass.

Validation reports must include coverage, counts, win rate, mean and total net
R, profit factor, drawdown, positive folds, fold variability, year/month/session
results, cost sensitivity, threshold sensitivity, and profit concentration for
both independent-candidate and execution-constrained views.

Lock at most one final policy. If none passes, lock none and keep the test set
closed.

## 16. Evaluation metrics

Classification:

```text
ROC-AUC, PR-AUC, log loss, Brier score, ECE,
precision, recall, F1, confusion matrix, probability reliability
```

Economic:

```text
coverage, accepted count, win rate, mean/median/total net R,
profit factor, maximum drawdown, payoff ratio, consecutive losses,
positive months/years/folds, base/higher/stress cost sensitivity
```

Stability:

```text
fold, year, month, direction, session, trend regime, volatility regime,
threshold sensitivity, feature-importance stability, profit concentration
```

## 17. Required artifacts

Each stage must save versioned configurations, dataset manifests, SHA-256
checksums, environment details, code commit, deterministic seeds, validation
reports, summary statistics, and known limitations. Training stages additionally
save models, predictions, metrics, calibration artifacts, feature importance,
and SHAP summaries where practical.

Do not overwrite or delete v1/v2 artifacts.

## 18. Future inference and LLM boundary

After a model and policy pass all research gates, a separate inference stage may
return structured JSON containing versions, probabilities, thresholds, pass
flags, deterministic signal, risk-filter status, and model-derived feature
contributions.

The LLM may later explain the structured decision in shadow mode. It must not
calculate indicators, invent feature values, modify probabilities, choose
direction, bypass risk controls, change stops or targets, size positions, or
override `NO_TRADE`. Live integration requires a separate specification and
approval.

## 19. Required tests

### Data and outcomes

- chronology, OHLC validity, duplicate and timezone checks;
- next-open entry and exact `t+1..t+48` horizon;
- frozen ATR and barrier calculations;
- TP, SL, expiry, censoring, and invalid-gap cases;
- same-M5-candle ambiguity and conservative SL-first fallback;
- verification that the outcome resolver never requests M1 data;
- gross, component cost, and net R calculations;
- deterministic outcome reruns.

### Features and joins

- no future data;
- closed M5/M15 boundaries and backward as-of joins;
- DST-aware session boundaries;
- warm-up and missing-value handling;
- exact candidate coverage and feature-contract hash;
- no outcome leakage into model inputs.

### Splits, models, and calibration

- chronology and timestamp-based outcome purging;
- next-entry offset and embargo enforcement;
- fixed test exclusion and CLI lock;
- fold-local preprocessing;
- deterministic predictions and artifact round trips;
- cross-fitted calibration and test isolation.

### Policy and execution

- directional threshold boundaries;
- both/neither pass produces `NO_TRADE`;
- ignored signals while a position is open;
- no opposing simultaneous positions;
- portfolio metrics use only executed trades;
- every hard safeguard is enforced;
- failed safeguards cannot be overridden by ranking.

## 20. Approval-gated implementation order

1. **Configuration proposal:** create schemas and propose the remaining split,
   concentration, total-count, and drawdown values. Stop for approval.
2. **Data audit:** verify the existing frozen source against the v3 contract.
   Stop if incompatible.
3. **`label_v3`:** implement and run bounded verification, then export the full
   separate outcome dataset and reports. Stop for label review and freeze.
4. **`feature_v3` specification:** define every exact formula. Stop for approval.
5. **Feature pipeline:** implement, test, and export features. Stop for review.
6. **Training dataset and protected splits:** build and validate. Stop for review.
7. **Baselines and untuned classifiers:** smoke locally; prepare full remote run.
8. **Ablation and optional later stages:** proceed only through separate approval.
9. **Policy selection:** validation/OOF only; lock at most one passing policy.
10. **Untouched test:** run once only after explicit approval and frozen checksums.
11. **Inference:** research interface only; no live integration.

## 21. Immediate authorised scope

Creating this document does not authorise implementation. The next executable
task, when explicitly requested, is milestone 1 only:

```text
Create and validate the v3 configuration schemas.
Propose fixed chronological split dates.
Propose the four remaining numeric policy safeguards.
Do not generate outcomes, features, models, or test predictions.
Stop for approval.
```

## 22. Definition of done

The research plan is complete only when every approval gate has passed, source
data and all contracts are frozen, deterministic label and feature pipelines are
validated, protected splits and cross-fitted calibration are verified, at most
one policy passes every safeguard, and the untouched test has been evaluated
once without feeding any result back into that policy.

Failure to find a passing policy is a valid outcome. It must be reported rather
than corrected by weakening safeguards or inspecting the test set.
