# msnr backtest results

```bash
.venv/bin/python -m scripts.history_provenance   # prove the data first
.venv/bin/python -m scripts.msnr_history_report
```

Run 2026-09-06 (UTC). Data: Binance monthly archives, **8.95 years**, BTCUSDT
and ETHUSDT, 1h (78,373 bars/symbol) and 4h confluence. Provenance: every
monthly archive individually SHA256-verified against Binance's published
digest at download time, the same guarantee every other report in this repo
relies on.

Scored under the corrected fixed-stop R model (`docs/r-model-correction.md`):
one third booked at each of TP1/TP2/TP3, the published stop never moves, so
an unbooked remainder loses its full share when the stop is hit.

`msnr` is the pinned strategy for `swing` (1h, all symbols) — it is the last
of the three original live sessions (`ict_fvg`/`super_scalp`, `cloud_mss`/
`scalp`, `msnr`/`swing`) never measured over long history before now.

## Headline

**`msnr` is not profitable, but it is a mild loser, not a decisive one** —
closer to `cloud_mss` (-0.046R) than to `ict_fvg` (-1.253R, pulled from live;
see `docs/ict-fvg-backtest-results.md`).

| Symbol | Years | Bars | Trades | TP1% | TP3% | Gross | **Net** | Total |
|---|---|---|---|---|---|---|---|---|
| BTCUSD | 8.95 | 78,373 | 2,817 | 50.3% | 16.4% | −0.000R | **−0.181R** | −508.5R |
| ETHUSD | 8.95 | 78,373 | 3,124 | 48.5% | 16.9% | −0.014R | **−0.157R** | −490.4R |

Pooled:

| n | Gross | **Net** | sd | t | 95% CI | Total |
|---|---|---|---|---|---|---|
| 5,941 | −0.007R | **−0.168R** | 1.139 | **−11.38** | **[−0.197, −0.139]** | −998.9R |

Gross is essentially flat (win rate ~49%, roughly a coin flip once the
0.5R/1R/2R-equivalent scale-out geometry is accounted for) — this is a
"no edge, modest cost drag" result, not a broken-mechanism result.

## No bugs found — a clean measurement on the first run

Unlike `ict_fvg`, this result needed no correction. Two things that went
wrong there don't apply here:

- **No near-zero-risk pathology.** `ict_fvg`'s stop was anchored to a swept
  bar up to 30 bars in the past while entry floated on the current close,
  fully decoupled — the mechanism that let risk collapse toward zero. `msnr`'s
  entry (`bar.close`) and its zone-derived stop are checked against the
  *same* signal bar (the rejection/retest condition requires that bar's
  high/low to already be touching the zone), so entry and stop can't drift
  apart between detection and firing. `_risk_ok()` still has no `MIN_STOP_ATR`
  floor (same as `ict_fvg` before its fix), but the tight same-bar coupling
  makes the degenerate geometry structurally far less likely — confirmed
  directly: sorted net R has min −2.43R / max +1.98R on both symbols, exactly
  where a clean scale-out model should land (full stop minus cost at the
  bottom, TP3 minus cost at the top). No fat tail: the worst 10 trades total
  only ~3.5% of each symbol's total loss (BTCUSD 3.7%, ETHUSD 3.4%) — fully
  broad-based, not outlier-driven.
- **No missing pipeline gate.** `super_scalp` had two extra deterministic
  hard gates in `signals/pipeline/scan.py` (session-hours, HTF-opposition)
  that the backtest had to replicate separately. `swing`/`msnr` has no
  equivalent special case there (checked). `msnr`'s HTF gate (`_long_ok`/
  `_short_ok`) is already a hard filter *inside* the detector itself, so
  `backtest_windowed`'s normal `htf_trend` plumbing — the same mechanism
  every other report in this repo already relies on — reproduces live
  behavior faithfully with no extra `gate=` callback needed.

## Chasing profitability: split by entry mode

```bash
.venv/bin/python -m scripts.msnr_tier_report
```

`msnr` fires through three entry modes: a rejection off a fresh body zone
(`rejection`), and two break-and-retest flips (`rbs` — resistance broken,
retested as support; `sbr` — support broken, retested as resistance).
Splitting the 5,941 trades:

| Mode | Share | Gross/trade | Net/trade | Gross t-stat |
|---|---|---|---|---|
| `rejection` | 24.9% | +0.023R | −0.146R | +0.77 |
| `sbr` | 35.2% | −0.002R | −0.158R | −0.06 |
| `rbs` | 39.9% | −0.032R | −0.191R | −1.36 |

Same conclusion as `ict_fvg`'s tier split, reached the same way: **no mode's
gross edge is statistically distinguishable from zero** (best case t=+0.77).
Unlike `ict_fvg`, there isn't even a theory-consistent ranking here — the
weakest reading (`rbs`) isn't dramatically different from the others, so
there's no subset worth carving out. This isn't a cost-drag story to fix
with a floor or a maker fill the way `ict_fvg` was; it's a "no detectable
edge, small persistent cost tax" story, consistent with 1h's much smaller
cost-to-risk ratio (net−gross is only ~0.16-0.19R here, versus ict_fvg's
~1.2R at 5m).

## Where msnr sits among strategies measured in this repo

| Strategy | Timeframe | Net per trade | Verdict |
|---|---|---|---|
| `bbma_reentry` | 1h/4h | +0.120R | **profitable** (the one winner) |
| `sr_limit` (maker) | 1h | −0.015R | flat |
| `bbma_extreme` | 1h | −0.019R | losing |
| `cloud_mss` | 15m | −0.046R | losing |
| **`msnr`** | **1h** | **−0.168R** | **losing, live** |
| `bbma_extreme` | short sweep | −0.153R | losing |
| `bbma_reentry` | 15m-equivalent scope | −0.137R | losing |
| `orb_rvol` | 15m | −0.238R | losing badly |
| `sr_zone` | 15m | −0.415R | losing badly |
| `ict_fvg` | 5m | −1.253R | losing badly (pulled from live) |

`msnr` runs at the same timeframe as this repo's one genuine winner
(`bbma_reentry`, 1h/4h), which rules out "wrong timeframe" as the
explanation the way it explained `ict_fvg`/`orb_rvol`/`sr_zone`'s losses.
The gap here is a rules problem, not a cost problem — `bbma_reentry`'s edge
comes from a specific pullback-continuation pattern with an HTF gate;
`msnr`'s body-zone rejection/break-retest pattern simply doesn't show a
measurable one at either timeframe scale tried above.

## What this means for delivery

**No code change was made to `TRADING_SESSIONS`.** This is a materially
different situation from `ict_fvg`: that result was decisive and severe
enough (t=−137.94, −1.253R/trade) to pull immediately. This one is mild and
in the same range as `cloud_mss` (−0.046R), which stayed live after its own
negative result. Whether to pull, tune, or leave `msnr` running is a call
worth making deliberately rather than as a reflex to any negative number —
surfaced here, not acted on unilaterally.

## Caveats

- **Crypto only.** Binance lists no gold, so `XAUUSD` (also live on `swing`)
  is not covered by this measurement.
- **BTC and ETH are correlated.** The pooled 5,941-trade sample is not 5,941
  independent observations, so the true confidence interval is somewhat
  wider than reported. It does not change the direction of this result — a
  t-statistic of −11.38 has real room to narrow and still be negative.
- **No profitability tuning was performed.** No parameter in
  `signals/strategies/msnr/` was changed before or because of this
  measurement.

## Follow-ups

This completes long-history measurement of all three of the engine's
original live sessions: `ict_fvg` (not profitable, pulled), `cloud_mss`
(mildly negative, kept), `msnr` (mildly negative, decision pending). None of
the three has shown a real edge over 8.9+ years — the only strategy in this
repository with a measured positive edge is `bbma_reentry`, at 1h/4h, not
currently pinned to any main session.
