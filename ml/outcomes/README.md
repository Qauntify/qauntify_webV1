# Outcome Resolver (`outcome_v1`)

`outcome_v1` resolves the immutable historical candidate dataset into a
separate dataset keyed by `candidate_id`. It does not modify candidate rows and
does not implement features, training splits, models, deployment, or live
trading behavior.

Policy source: `ml/configs/outcome_v1.yaml`.

- Entry is a market fill at the candidate decision close and `entry_price`.
- TP1, TP2, and TP3 each close the configured one-third position fraction.
- The initial stop remains fixed for the unresolved position.
- M5, M15, and H1 candidates expire after 1, 2, and 14 days respectively.
- A primary candle touching both stop and an unhit target is inspected using
  M1, M5, or M15 candles respectively.
- Lower-timeframe data must completely cover the parent candle. Missing or
  still-ambiguous data resolves stop-first conservatively.
- `lower_timeframe_resolutions` and `conservative_fallbacks` are not mutually
  exclusive counters. The first counts ambiguous parent candles for which a
  complete lower-timeframe slice was inspected. The second counts cases that
  ultimately required stop-first handling, either because lower-timeframe
  coverage was incomplete or because TP and SL remained tied within one
  lower-timeframe candle. A complete slice with a remaining intrabar tie is
  therefore included in both counts.
- An expiry closes the remaining position at the final available close before
  expiry.
- Candidates without enough right-edge data are `right_censored`; realized R
  remains null.
- MFE and MAE are expressed as non-negative multiples of initial risk.
- Net R subtracts the versioned 0.05R round-trip cost estimate.

```powershell
python -m ml.outcomes.cli --config ml/configs/outcome_v1.yaml --dry-run --limit 100
python -m ml.outcomes.cli --config ml/configs/outcome_v1.yaml
python -m ml.outcomes.cli --config ml/configs/outcome_v1.yaml --overwrite
```

Generated outputs:

```text
ml/data/processed/outcomes/outcome_manifest.json
ml/data/processed/outcomes/strategy_name=.../timeframe=.../outcome_class=.../year=.../*.parquet
ml/data/reports/outcome_v1.json
ml/data/reports/outcome_v1.md
```
