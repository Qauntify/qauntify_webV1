# cloud_mss backtest results

```bash
.venv/bin/python -m scripts.history_provenance   # prove the data first
.venv/bin/python -m scripts.cloud_mss_report
```

Run 2026-07-31 (UTC). Data: Binance monthly archives, **8.87 years**, BTCUSDT
and ETHUSDT, 15m primary with 1h for the cloud, 310,462 bars per symbol.
Provenance is established by `scripts/history_provenance.py` — SHA256 against
Binance's published digests plus known market events at their correct dates.

Scored under the corrected fixed-stop R model
(`docs/r-model-correction.md`): one third booked at each of TP1/TP2/TP3, the
published stop never moves, so an unbooked remainder loses its full share when
the stop is hit.

## Headline

**`cloud_mss` is not profitable.** It is negative at every stop-width cap
tested, and it is deployed anyway at the operator's explicit direction.

| Cap (ATR) | Trades | TP1% | Gross | **Net** | t |
|---|---|---|---|---|---|
| 2.5 | 35 | 51.4% | −0.045R | −0.298R | −1.43 |
| 4.0 | 325 | 47.4% | +0.030R | **−0.137R** | −1.90 |
| **6.0 (shipped)** | **1,202** | **50.2%** | **+0.060R** | **−0.046R** | **−1.24** |
| 8.0 | 1,390 | 50.2% | +0.044R | −0.048R | −1.42 |

At the shipped cap: **−0.046R per trade over 1,202 trades, −55.0R total.**

## Why the stop cap is 6.0 and not 2.5

This was a real defect in the design, found only by measuring.

`sr_zone` and both BBMA detectors cap stops at 2.5 ATR. The spec specified the
same for `cloud_mss` without checking it against where this strategy actually
puts its stop — the far edge of the cloud. That edge is a 1h Chandelier band
sitting 4.5× the **one-hour** ATR from its extreme. Expressed in the **15m**
ATR that `MAX_STOP_ATR` divides by, it is 6–9 ATR before the pullback distance
is added.

Measured across 310,462 bars with the cap disabled:

- 4,356 setups exist
- median stop width **6.6 ATR**
- only **27 (0.6%)** fit inside 2.5 ATR

So the two constants described incompatible worlds. At 2.5 the strategy fired
35 times in 8.87 years — roughly twice per symbol per year. That is not
selectivity, it is a detector that was never allowed to trade.

6.0 comes from the sweep above: the point where trade count stops rising
materially and net expectancy is least bad. **It does not rescue the strategy.**
Raising the cap bought volume (35 → 1,390 trades) and produced no edge, which
is the cleanest possible read — the cap was throttling frequency, not hiding a
winner.

## Reading the result

Gross expectancy is barely positive (+0.03R to +0.06R) and round-trip costs
take it under water. This is the same shape as every other strategy measured in
this repository:

| Strategy | Net per trade | Verdict |
|---|---|---|
| `sr_limit` 1h (maker) | −0.015R | flat |
| `bbma_reentry` | −0.137R | losing |
| `bbma_extreme` | −0.153R | losing |
| `sr_zone` 15m (taker) | −0.415R | losing badly |
| **`cloud_mss` 15m** | **−0.046R** | **losing** |

Five strategies, nine years of verified data, none profitable. The common
factor is not any one playbook — it is that a gross edge of +0.03R to +0.2R
does not survive realistic transaction costs at these timeframes.

With 1,202 trades the confidence interval is tight enough that "the sample is
too small" is not available as an explanation.

## What was shipped anyway

The 15m session runs `cloud_mss`. The slot previously ran `sr_zone` (−0.415R)
and was retired; it is scanned again here.

On the measured numbers alone this strategy would not ship, and the
implementation plan committed to reverting the session change if it failed.
That gate was overridden deliberately by the operator, with the figures above
in hand. This section exists so that decision is legible later rather than
looking like an oversight.

`cloud_mss` at −0.046R is roughly nine times less costly per trade than the
`sr_zone` stream it replaces, so the 15m slot is materially better than it was
— but "better than the worst thing we measured" is not the same as profitable.

## What this work leaves behind regardless

- **Multi-timeframe backtesting.** `backtest_windowed` now feeds detectors an
  aligned higher-timeframe candle slice, passing only candles that had CLOSED
  by each primary bar. `backtest.py` previously stated multi-timeframe
  strategies were not covered. This also unblocks measuring `ce_lwma`, which
  has never been tested over long history.
- **`sma_atr`**, MetaTrader's simple-average true range, so a Chandelier band
  drawn by the engine matches the chart a human reads it from.

## Follow-ups

1. **Measure `ce_lwma`.** It is the other multi-timeframe strategy and has
   never been tested past a few months. The harness now supports it.
2. **Measure `ict_fvg` at 5m.** It is live on the super-scalp session, has
   never been measured over long history, and runs on the fastest timeframe in
   the engine — where cost drag is worst.
3. **Attack costs, not rules.** Five strategies have now failed the same way.
   The evidence points at execution cost rather than any individual playbook.
