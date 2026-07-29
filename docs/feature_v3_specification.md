# feature_v3 Specification

## Scope

`feature_v3` is keyed by the frozen `label_v3_1.candidate_id`. Features describe
the completed M5 decision candle and the most recent fully completed M15 candle.
No future price, label, outcome, target, cost result, or test-derived statistic
may enter the feature dataset.

## Timestamp alignment

Source timestamps are candle-open times. For M5 row `t`, decision time is
`M5.open_time + 5 minutes`. For M15 row `j`, availability time is
`M15.open_time + 15 minutes`. Context uses a backward as-of join satisfying:

```text
M15.available_time <= M5.decision_time
```

No M15 candle that is still forming may be used. No values may be carried across
either audited material source gap.

## Numeric conventions

- EMA is seeded by the SMA of its first complete period and uses
  `alpha = 2/(period+1)`.
- ATR, RSI, ADX, DI+ and DI- use Wilder smoothing.
- Standard deviation uses population `ddof=0`.
- Log return over `k` bars is `ln(close[t]/close[t-k])`.
- A normalized distance `(a-b)/ATR14` is null when ATR14 is unavailable or zero.
- Boolean states are stored as integer 0/1.
- Infinite values are forbidden.

## M5 features

Trend:

- EMA 9, 20, 21, 50, 100 and 200;
- SMA 10, 20, 50, 100 and 200;
- close-to-average distances divided by ATR14;
- adjacent configured EMA gaps divided by ATR14;
- three-bar EMA slopes `(EMA[t]-EMA[t-3])/ATR14[t]`;
- bullish and bearish EMA ordering flags.

Momentum:

- RSI 7, 14 and 21;
- one- and three-bar RSI changes;
- MACD(12,26,9) line, signal and histogram;
- log rate of change over 3, 6 and 12 bars.

Volatility and bands:

- Wilder ATR 7, 14 and 21;
- ATR divided by close;
- Bollinger(20,2) upper, middle and lower bands;
- band width `(upper-lower)/middle`;
- band position `(close-lower)/(upper-lower)`;
- close-to-band distances divided by ATR14;
- rolling population standard deviation of one-bar log returns over 12 and 48 bars.

Trend strength:

- ADX14, DI+14, DI-14 and `DI+ - DI-`.

Candle geometry:

- range and range/ATR14;
- signed body `(close-open)/ATR14`;
- absolute body/range;
- upper wick/range and lower wick/range;
- close position `(close-low)/range`;
- bullish and bearish flags;
- log returns over 1, 3, 6 and 12 bars.

For a zero-range candle, all range-ratio features equal zero.

Deterministic BBMA states:

- `close_above_upper`, `close_below_lower`;
- `close_above_middle`, `close_below_middle`;
- `ema9_above_middle`, `ema9_below_middle`;
- bullish re-entry: previous close above upper and current close at/below upper;
- bearish re-entry: previous close below lower and current close at/above lower.

## M15 context features

Apply the same formulas on M15 for EMA 20/50/200, RSI14, ATR14, ADX14,
DI+14, DI-14, Bollinger(20,2), band width and band position. Prefix every field
with `m15_`. Also store M15 candle age in minutes at decision time; it must be
between zero and less than 15 minutes for normally aligned data.

## Eligibility and exclusions

A row becomes feature-eligible only after 200 complete historical bars exist on
both timeframes and every required value is finite. Warm-up values are not
imputed. Rows affected by audited material gaps are ineligible until each
timeframe independently rebuilds the required history.

Timezone-dependent hour/session/calendar features and all volume-derived
features are excluded because their source semantics are not verified.

## Required validation

- exact one-to-one candidate coverage with `label_v3_1`;
- deterministic rerun checksums;
- closed-candle M5 and M15 boundary tests;
- future-candle mutation leakage tests;
- gap-reset and warm-up tests;
- no target/outcome fields;
- no infinities;
- stable schema and dtype manifest.

