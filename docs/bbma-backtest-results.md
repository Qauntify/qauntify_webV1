# BBMA backtest results

Run 2026-07-27 (UTC) with:

```bash
.venv/bin/python -m scripts.bbma_report
```

Design: `docs/superpowers/specs/2026-07-27-bbma-strategy-design.md`

## Raw sweep

```
Scale-out model: 1/3 booked at each of TP1/TP2/TP3, stop to breakeven after TP1. Net subtracts r_model round-trip costs.
bbma_extreme ladder is 0.5/1/1.5R; bbma_reentry is 1/2/3R.
strategy      symbol  tf   bars trades   tp1%   tp3%   gross     net     totR
------------------------------------------------------------------------------
bbma_extreme  BTCUSD  1h    720     19  73.7%  57.9%  +0.34R  -0.00R    +6.5R
bbma_extreme  ETHUSD  1h    720     22  72.7%  36.4%  +0.17R  -0.06R    +3.7R
bbma_extreme  XAUUSD  1h   1432     42  69.0%  35.7%  +0.18R  +0.15R    +7.7R
bbma_extreme  GBPUSD  1h    720     17  76.5%  29.4%  +0.20R  +0.09R    +3.3R
bbma_extreme  BTCUSD  4h    720     19  63.2%  42.1%  +0.12R  +0.00R    +2.3R
bbma_extreme  ETHUSD  4h    720     20  70.0%  40.0%  +0.20R  +0.11R    +4.0R
bbma_extreme  XAUUSD  4h    762     28  50.0%  39.3%  -0.09R  -0.10R    -2.5R
bbma_extreme  GBPUSD  4h    720     21  81.0%  52.4%  +0.44R  +0.39R    +9.3R
bbma_reentry  BTCUSD  1h    720      3  33.3%   0.0%  -0.33R  -0.52R    -1.0R
bbma_reentry  ETHUSD  1h    720      4  50.0%   0.0%  -0.17R  -0.30R    -0.7R
bbma_reentry  XAUUSD  1h   1432      6  83.3%  16.7%  +0.61R  +0.58R    +3.7R
bbma_reentry  GBPUSD  1h    720      3  33.3%  33.3%  +0.00R  -0.08R    +0.0R
bbma_reentry  BTCUSD  4h    720      2  50.0%   0.0%  -0.33R  -0.42R    -0.7R
bbma_reentry  ETHUSD  4h    720      3  66.7%  33.3%  +0.44R  +0.37R    +1.3R
bbma_reentry  XAUUSD  4h    762      4  75.0%  25.0%  +0.75R  +0.74R    +3.0R
bbma_reentry  GBPUSD  4h    720      4   0.0%   0.0%  -1.00R  -1.04R    -4.0R
```

## Pooled per-trade statistics

Row-level averages over 2–20 trades are not readable on their own, so the same
trades were pooled across every symbol and timeframe:

| Strategy | n | Gross | Cost drag | Net | 95% CI on net | t |
|---|---|---|---|---|---|---|
| `bbma_extreme` | 188 | +0.183R | −0.106R | **+0.076R** | [−0.046, +0.199] | 1.22 |
| `bbma_reentry` | 29 | +0.057R | −0.074R | **−0.016R** | [−0.437, +0.405] | −0.08 |

## How to read this

**The samples are small, and the reason is structural.** Kraken caps its OHLC
endpoint at 721 bars regardless of the requested limit and serves no deeper
history, so a 1h row spans ~30 days and a 4h row ~120 days per symbol. XAUUSD
is the one exception (Yahoo, 1432 bars at 1h). Pagination cannot extend the
Kraken series — the data simply is not offered.

Any single row here is noise. A row with 2–6 trades carries no information at
all, whichever direction it points. The pooled figures are the only numbers in
this document worth weighing, and even those are thin.

**Costs are not a footnote for these strategies.** `bbma_extreme` books its
first third at 0.5R of a deliberately tight stop, and cost expressed in R
scales inversely with stop distance. Round-trip costs consumed **58% of its
gross edge** (+0.183R → +0.076R). Quoting the gross number alone would have
made this look roughly twice as good as it is.

## Verdict

The bar set in the design was *positive net expectancy on more than one symbol
with a non-trivial trade count*.

### `bbma_extreme` — does not clear the bar. Not promoted.

The encouraging part is real: gross expectancy is positive on 7 of 8 rows, the
TP1 hit rate is consistently 63–81%, and the pooled net is positive.

It still fails, for two reasons.

1. **The edge is smaller than its own sampling error.** +0.076R over 188 trades
   carries a 95% confidence interval of [−0.046, +0.199], which straddles zero
   (t = 1.22). This data cannot distinguish the strategy from a coin flip.
2. **The sign is unstable across timeframes on the same instrument.** XAUUSD
   pays +0.15R at 1h and −0.10R at 4h; BTCUSD is −0.00R at 1h and +0.00R at 4h.
   A real effect should not reverse when the bar length changes while the rules
   stay identical.

### `bbma_reentry` — cannot be evaluated. Not promoted.

29 trades across eight rows, 2–6 per row. The 95% CI of [−0.437, +0.405] spans
almost a full R in each direction. This is not a negative result; it is the
absence of a result. Nothing about the setup's quality can be inferred, in
either direction, from this data.

The notable fact is the *frequency* gap: Re-entry fired 29 times where Extreme
fired 188, on identical candles. Six conditions have to align simultaneously
(momentum leg, rising Mid BB, EMA50 side, MA5 pullback, MA10 hold, Mid BB
hold), and at least one is evidently near-binding. That is a fact about the
implementation's restrictiveness, not yet about the setup's edge.

## Follow-ups worth doing

1. **Find which Re-entry rule is binding.** Instrument the detector to count
   how many bars pass each of the six conditions, then relax only the one that
   is throttling the rest. Until the trade count reaches the low hundreds, no
   verdict on Re-entry means anything. This is the highest-value next step —
   the current answer is "unknown", not "bad".
2. **Test the ADX veto on Extreme.** `adx14` is already recorded into every
   emitted setup's `indicators` precisely so this can be answered from stored
   data rather than by re-running with a guessed threshold. `sr_zone` vetoes
   mean-reversion above ADX 35 for the same reason; if Extreme's losers cluster
   in strong trends, that veto is free.
3. **Get deeper history before re-deciding.** The binding constraint on this
   whole exercise is 721 bars. The `ml/data/` pipeline points at a HuggingFace
   XAUUSD set covering 2004–2025 at every timeframe, which would give one
   instrument a genuinely long test — though it is gold-only and lives in the
   ML tree, which is not wired into the live engine.

## What shipped regardless

The sweep also surfaced and fixed a pre-existing data bug: `YAHOO_INTERVAL`
mapped a 4h gold request to Yahoo's hourly series, so `fetch_candles("XAUUSD",
"4h")` returned 60-minute bars (measured: 2,829 bars at a 60.0m median gap).
Because `backtest.py` uses 4h for HTF confluence on every strategy, XAUUSD's
higher-timeframe trend was being computed from 1h data while labelled 4h — for
`ema_cross`, `ict_smc` and `sr_zone` too, not only BBMA. Gold's 4h series is
now folded into true 4h buckets (763 bars, 240.0m median gap).
