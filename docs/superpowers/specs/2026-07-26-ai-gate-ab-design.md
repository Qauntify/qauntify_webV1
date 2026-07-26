# Measuring whether the LLM confirmation gate earns its keep

## Goal

Decide, from evidence, whether the LLM confirm/reject step improves trade
outcomes. Today it **rejects 87% of the setups the rules engine finds** (729 of
837 evaluated, 2026-07-07 → 2026-07-26) and nothing has ever measured whether
the trades it discards were worse than the ones it keeps.

## Why this cannot be answered today

A rejected setup never becomes a signal, so its outcome is never recorded. The
gate's accuracy is structurally unobservable — the counterfactual is thrown
away at the moment of the decision.

A forward simulation on historical candles was run on 2026-07-26 as a first
pass:

| Arm | n | Win rate | Mean R |
|---|---|---|---|
| confirm | 62 | 51.6% | +0.172R |
| reject | 57 | 66.7% | +0.374R |

Rejected setups did *better*, but the difference does not survive testing:
Welch t = +0.91, permutation test **p = 0.359**. That is not evidence the gate
is harmful — it is evidence the sample is far too small to tell either way.
This design exists to fix the sample, not to confirm a suspicion.

## Approach: shadow signals

When the LLM rejects a setup, store it as a **shadow signal** — full entry,
stop and targets, tracked by the existing outcome tracker — but never delivered
anywhere a user can see it.

Rejected alternatives:

- **Live A/B (send a fraction of rejected setups to subscribers).** Truly
  measures execution too, but deliberately pushes trades the system flagged as
  bad to paying users. Not acceptable.
- **More backtesting.** Free, but bounded by history and by proxy-data quality;
  it is what produced the underpowered result above, and it accumulates no
  faster than reality.

Shadow mode gets the same statistical power as a live A/B with **zero
user-facing risk**, because the measurement path (outcome tracker) is identical
to the one already used for real signals.

## What must not leak

A shadow signal is not a recommendation. It must be excluded from:

| Surface | Requirement |
|---|---|
| Telegram | never sent |
| `/track-record` | excluded from every stat — equity curve, win rate, breakdowns |
| Public dashboard | not listed |
| Setup / outcome charts | not rendered (also saves render cost) |
| Anon RLS policy | must not expose shadow rows |

The existing anon RLS policy exposes closed trades to the public track-record
page. Shadow rows are closed trades by every other definition, so **the policy
must be tightened before any shadow row is written**, not after.

## Pre-registered analysis

Fixed in advance, because deciding the test after seeing the data is how noise
gets promoted to a finding.

- **Primary metric:** mean realised R per trade, under the existing scale-out
  model (⅓ booked at each target, stop to breakeven after TP1).
- **Comparison:** confirmed vs shadow-rejected, pooled across symbols.
- **Test:** two-sided permutation test on the difference of means, α = 0.05.
- **Stratification (secondary, reported but not decisive):** by strategy,
  timeframe, and LLM confidence bucket.
- **Stopping rule:** n = 250 per arm, or 60 days, whichever comes first. No
  peeking-and-stopping early on a favourable result.

### Decision rule

| Outcome | Action |
|---|---|
| Confirmed significantly better | Keep the gate. Consider raising the confidence floor. |
| No significant difference | The gate costs LLM spend and 87% of trade flow for no measured benefit — retune or remove it. |
| Rejected significantly better | Remove or invert the gate. |

## Statistical power — how long this actually takes

Observed per-trade dispersion is σ ≈ 1.2R. Required sample per arm for 80%
power at α = 0.05:

| Difference to detect | n per arm | Days at current rate |
|---|---|---|
| 0.5R | 90 | ~16 |
| 0.4R | 141 | ~25 |
| 0.3R | 251 | ~44 |
| 0.2R | 565 | ~99 |

**The confirmed arm is the bottleneck**, at ~5.7 confirms/day (108 over 19
days). Rejects arrive at ~38/day, roughly 7× faster.

Two consequences:

1. Running this for two weeks will settle nothing. **Six weeks is the realistic
   minimum**, to detect a 0.3R difference.
2. Because rejects are so much more plentiful, they can be **sampled down to
   ~10/day** without affecting the timeline — the confirmed arm still gates it.
   That keeps storage and outcome-tracking load roughly flat instead of 8×.

## Implementation sketch

| File | Change |
|---|---|
| `supabase/` migration | `signals.shadow boolean not null default false`; tighten the anon RLS policy to `shadow = false` |
| `signals/run.py` | in the `event_kind="reject"` path, sample at `SHADOW_SAMPLE_RATE` and `save_signal(..., shadow=True)` |
| `signals/storage.py` | persist the flag; exclude shadows from `list_closed_signals` unless explicitly requested |
| `signals/outcome_tracker.py` | poll shadow signals exactly like real ones |
| `signals/telegram_client.py` | never send a shadow |
| `signals/run.py` chart step | skip chart rendering for shadows |
| `web/src/lib/track-record.ts` | filter `shadow = false` (belt and braces — RLS should already prevent it) |
| `scripts/gate_report.py` | new: run the pre-registered permutation test on demand |

## Risks

- **Leakage of shadow rows to the public page.** Mitigated by tightening RLS
  *before* the first write, plus a client-side filter. Worth an explicit test.
- **Outcome-tracker load.** Controlled by `SHADOW_SAMPLE_RATE` (~10/day).
- **Selection effect on the reject arm.** If rejects are sampled, sample
  **randomly**, never by confidence or symbol, or the comparison is biased.
- **Regime confounding.** Six weeks is one regime. A positive result means "the
  gate helped in this period", not "the gate works".

## Out of scope

Changing the gate's prompt, model, or confidence thresholds while the
experiment runs — any mid-flight change invalidates the sample.
