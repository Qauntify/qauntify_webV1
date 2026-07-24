# Historical Feature Pipeline (`feature_v1`)

This offline pipeline creates one immutable feature row per replay candidate. It
does not read outcomes, create training splits, train models, or affect the live
signal engine.

## Causal boundary

The candidate's `source_candle_timestamp` identifies the final candle supplied
to the production strategy. That candle is included because it is closed when
`candidate_timestamp` occurs. Every indicator, rolling window, structure level,
FVG, S/R zone, and strategy-specific value is calculated from a read-only prefix
ending at that source candle. Candles whose open timestamp is at or after the
candidate timestamp are never visible to the row calculator.

Production implementations are reused for EMA9/21, RSI14, MACD histogram,
ATR14, ADX14, pivot/FVG/S/R detection, higher-timeframe trend, and the final
strategy detector parity check.

The resulting dataset is keyed by `candidate_id`, partitioned by strategy,
timeframe, and candidate year, and retains candidate/candle manifest provenance.
It deliberately contains no outcome or label columns.
