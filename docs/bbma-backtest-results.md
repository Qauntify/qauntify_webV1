# BBMA backtest results

Design: `docs/superpowers/specs/2026-07-27-bbma-strategy-design.md`

**Headline: the two patterns finished in opposite places, and the long test
reversed the short one.**

- `bbma_reentry` — **+0.120R net per trade over 905 trades and 8.87 years**,
  profitable in 7 of 10 calendar years. A genuine candidate.
- `bbma_extreme` — **−0.019R net over 6,136 trades**, profitable in 3 of 10
  years, **−117.8R total**. Rejected.

The first sweep (four months, below) pointed the other way on both. That is
what a four-month sample is worth.

---

## 1. Long-history test — the decisive one

```bash
.venv/bin/python -m scripts.history_provenance   # prove the data first
.venv/bin/python -m scripts.bbma_history_report
```

Data: Binance monthly archives, **2017-08-17 → 2026-06-30, 8.87 years**,
BTCUSDT and ETHUSDT, 1h and 4h. Replayed on a 200-bar rolling window, matching
the `ScanConfig.candle_limit` the live scan actually sees.

### Why this data is trusted

Provenance is established two independent ways, because "I downloaded a file"
is not evidence (`scripts/history_provenance.py`):

1. **Cryptographic** — all 107 monthly archives verified against Binance's
   published SHA256 before parsing. Fail-closed on mismatch.
2. **Historical** — checksums prove a file is unmodified, not that its contents
   are real prices. So known market events were located in the data:

| Landmark | Found | Expected |
|---|---|---|
| 2017 blow-off top | $19,799 on 2017-12-17 12:00 | Dec 2017, $17–21k |
| 2018 bear low | $3,156 on 2018-12-15 15:00 | Dec 2018, $3.0–3.6k |
| COVID crash low | $3,782 on 2020-03-13 02:00 | 11–14 Mar 2020, $3.5–4.5k |
| 2021 all-time high | $69,000 on 2021-11-10 14:00 | Nov 2021, $66–71k |
| FTX collapse low | $15,476 on 2022-11-21 21:00 | Nov 2022, $15–16.5k |

Worst single hour in 8.87 years: **−18.2% on 2020-03-12 10:00 UTC** — Black
Thursday, to the hour. Plus 126 missing hours across 29 discontinuities, which
are real exchange outages; a simulated series has none.

### Results

| Strategy | Symbol | tf | Trades | TP1% | TP3% | Gross | Net | Total |
|---|---|---|---|---|---|---|---|---|
| `bbma_extreme` | BTCUSD | 1h | 2505 | 65.5% | 38.9% | +0.120R | **−0.054R** | −134.8R |
| `bbma_extreme` | ETHUSD | 1h | 2433 | 65.0% | 38.2% | +0.112R | **−0.017R** | −42.5R |
| `bbma_extreme` | BTCUSD | 4h | 598 | 64.5% | 40.0% | +0.120R | +0.035R | +20.9R |
| `bbma_extreme` | ETHUSD | 4h | 600 | 64.3% | 41.7% | +0.126R | +0.064R | +38.6R |
| `bbma_reentry` | BTCUSD | 1h | 336 | 52.4% | 29.5% | +0.238R | **+0.089R** | +29.8R |
| `bbma_reentry` | ETHUSD | 1h | 367 | 51.2% | 27.8% | +0.196R | **+0.089R** | +32.8R |
| `bbma_reentry` | BTCUSD | 4h | 106 | 52.8% | 33.0% | +0.321R | **+0.250R** | +26.5R |
| `bbma_reentry` | ETHUSD | 4h | 96 | 49.0% | 34.4% | +0.253R | **+0.200R** | +19.2R |

Pooled:

| Strategy | n | Gross | Net | t | 95% CI | Total |
|---|---|---|---|---|---|---|
| `bbma_extreme` | 6136 | +0.117R | −0.019R | −1.72 | [−0.041, +0.003] | −117.8R |
| `bbma_reentry` | 905 | +0.232R | **+0.120R** | **+2.77** | **[+0.035, +0.204]** | +108.3R |

### Per-year breakdown — the robustness test

`bbma_reentry`:

| Year | Trades | Net/trade | Total |
|---|---|---|---|
| 2017 | 48 | +0.210R | +10.1R |
| 2018 | 88 | +0.395R | +34.7R |
| 2019 | 97 | +0.161R | +15.6R |
| 2020 | 96 | +0.441R | +42.3R |
| 2021 | 117 | −0.060R | −7.0R |
| 2022 | 96 | +0.089R | +8.6R |
| 2023 | 92 | −0.011R | −1.0R |
| 2024 | 98 | +0.090R | +8.8R |
| 2025 | 113 | +0.016R | +1.8R |
| 2026 | 60 | −0.093R | −5.6R |

**7 of 10 years positive. Median trade +0.157R** (above the mean, so not
outlier-driven). The **top 10 trades contribute only +19.7R of the +108.3R
total — 18%**, so the result is broad-based rather than a few lucky wins.

Its two best years were **2018 (+34.7R, the bear market)** and **2020 (+42.3R,
the COVID crash)** — the stress regimes. Its one meaningful losing year was
**2021, the parabolic bull**, which is coherent: a pullback-continuation setup
with an HTF gate gets little to work with in a melt-up that never pulls back.
Losing years are small (−7.0R, −1.0R, −5.6R); winning years are large.

`bbma_extreme`, by contrast: **3 of 10 years positive**, and the shape of the
failure is instructive. Median trade **+0.119R** against a mean of **−0.019R**
— it wins 65% of the time with a positive median and still loses money, because
the losers are far bigger than the winners. That is the textbook mean-reversion
payoff: picking up pennies in front of a steamroller. No parameter change fixes
a payoff shape.

### This was out-of-sample

Not one parameter was touched between the four-month sweep and the nine-year
run — `git diff` over `signals/strategies/bbma/` across those commits is empty.
The lookbacks (6, 10), the 0.5 ATR stop buffer and the 2.5 ATR cap all came
from BBMA doctrine and this repo's existing `sr_zone` conventions, fixed before
any long-history data was seen. **No optimisation was performed at any point.**
That matters more than the t-statistic: the usual reason a backtest fails
forward is that its parameters were fitted to the test set, and here there was
no fitting to do.

---

## 2. Short sweep — superseded, kept as a cautionary record

```bash
.venv/bin/python -m scripts.bbma_report
```

Run 2026-07-27 over Kraken/Yahoo live data — 30 days at 1h and 120 days at 4h
per symbol, because Kraken caps OHLC at 721 bars.

| Strategy | n | Gross | Net | 95% CI |
|---|---|---|---|---|
| `bbma_extreme` | 188 | +0.183R | +0.076R | [−0.046, +0.199] |
| `bbma_reentry` | 29 | +0.057R | −0.016R | [−0.437, +0.405] |

Both readings were wrong in direction. Extreme looked like the promising half
and is the loser; Re-entry looked unmeasurable — which was the correct call at
29 trades — and is the winner. The four-month window (2026-03 to 2026-07) was a
single regime that happened to suit a mean-reversion setup.

**The lesson is the sample, not the strategies.** Any conclusion drawn from
four months of one regime is a coin flip wearing a decimal point.

---

## Verdict

### `bbma_reentry` — promote to a paper trial

It clears the bar set in the design and then some: positive net expectancy on
every symbol and timeframe tested, 7 of 10 years positive, a positive median,
not outlier-driven, statistically significant (t = +2.77, CI excludes zero),
and profitable through both a bear market and a liquidity crash — on unfitted
parameters.

Caveats that keep this a paper trial rather than a live promotion:

- **The CI is optimistic.** BTC and ETH are highly correlated and the 1h/4h
  rows cover the same underlying market, so 905 trades are not 905 independent
  observations. The true interval is wider than [+0.035, +0.204].
- **Crypto only.** Binance lists no gold or GBP, so `XAUUSD` and `GBPUSD` are
  still on four months of data.
- **Costs take 48%** of the gross edge (+0.232R → +0.120R). At a worse fee tier
  than the 20bps in `r_model.COST_BPS`, the edge shrinks toward zero. Confirm
  the tier before sizing anything.
- **4h is the stronger timeframe** (+0.250R / +0.200R vs +0.089R at 1h), for
  the same reason Extreme fails at 1h: wider stops mean cost is a smaller
  fraction of R.

### `bbma_extreme` — reject

−117.8R over 6,136 trades and nine years, positive in 3 of 10. The 4h rows are
mildly positive, but that is two rows out of four in a strategy whose pooled
result is negative and whose payoff shape is structurally adverse.

The limit-entry idea floated after the short sweep should **not** be pursued on
the strength of that sweep — it was built on a false positive. If it is ever
revisited, the argument has to be made against these nine-year numbers.

## Follow-ups

1. **Paper-trial `bbma_reentry` at 4h**, where the cost drag is smallest. This
   needs a session slot decision, an admin-selectable entry with its migration,
   and a chart-plan builder — none of which this work did.
2. **Extend gold and FX history.** The HuggingFace XAUUSD set in `ml/data/`
   covers 2004–2025 and would test Re-entry on a genuinely different asset
   class; it needs `requirements-ml-data.txt` installed. FX would need a source
   such as HistData.
3. **Re-run the other strategies over this history.** `sr_zone`, `sr_limit` and
   `orb_rvol` are all sitting on the same thin evidence the short BBMA sweep
   was. `signals/history.py` is strategy-agnostic and the sweep pattern is now
   established.

## Incidental fix

`YAHOO_INTERVAL` mapped a 4h gold request to Yahoo's hourly series, so
`fetch_candles("XAUUSD", "4h")` returned 60-minute bars (2,829 bars at a 60.0m
median gap). Because `backtest.py` uses 4h for HTF confluence on every strategy,
XAUUSD's higher-timeframe trend was computed from 1h data while labelled 4h —
for `ema_cross`, `ict_smc` and `sr_zone` too. Now folded into true 4h buckets
(763 bars, 240.0m median gap).
