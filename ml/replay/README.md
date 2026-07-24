# Historical Strategy Replay

This package replays the repository's deterministic production strategy rules
over validated XAUUSD candles and records rule-generated candidates. It does
not call the LLM confirmation layer, broker APIs, Telegram, Supabase, outcome
tracking, feature engineering, or model code.

## Active strategy configuration

`ml/configs/strategy_replay_v1.yaml` mirrors the default production streams:

| Primary timeframe | Strategy | Closed confluence timeframe |
|---|---|---|
| M5 | `ict_fvg` | M15 |
| M15 | `sr_zone` | none |
| H1 | `ema_cross` | H4 |

The adapter calls `signals.strategies.detect_setup`, using the same causal
indicator implementations and unchanged detector thresholds as live scans.
Selectable but inactive strategies are not enabled automatically.

## Closed-candle timestamp policy

The cleaned source timestamp is treated as candle open time, matching the
production `Candle.open_time` contract. A detector is invoked only after that
candle is closed. Therefore `source_candle_timestamp` is the candle open time,
while `candidate_timestamp` and the logical `created_at` are open time plus the
timeframe duration. This keeps records deterministic.

Higher-timeframe confluence uses only an HTF candle whose close time is no
later than the primary candle's open time, matching the existing production
backtest alignment policy.

## Commands

```bash
python -m ml.replay.cli --config ml/configs/strategy_replay_v1.yaml \
  --timeframe M5 --start 2024-01-01 --end 2024-01-07 --dry-run

python -m ml.replay.cli --config ml/configs/strategy_replay_v1.yaml

python -m ml.replay.cli --config ml/configs/strategy_replay_v1.yaml --overwrite
```

Useful filters are `--symbol`, `--timeframe`, `--strategy`, `--start`,
`--end`, and `--limit`. Reads use Arrow partition filters, and timeframes are
processed independently.

## Output and safety

```text
ml/data/processed/candidates/
|-- candidate_manifest.json
`-- symbol=XAUUSD/timeframe=M5/strategy_name=ict_fvg/year=YYYY/*.parquet
```

The versioned `candidate_v1` schema contains setup prices, risk geometry,
stable IDs, detector source hashes, dataset provenance, and decision times.
Outcome labels and future-derived fields are forbidden. Existing output is
fully staged and replaced with rollback protection only with `--overwrite`.

Leakage controls include prefix-only detector inputs, causal production
indicators sliced at the current index, already-closed HTF alignment, and no
centered windows, negative shifts, backfills, or forward outcome access.

