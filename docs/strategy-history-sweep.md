# Every strategy re-measured over 8.87 years

Run 2026-07-28.

```bash
.venv/bin/python -m scripts.history_provenance   # prove the data first
.venv/bin/python -m scripts.history_sweep
```

Data: Binance monthly archives, 2017-08-17 → 2026-06-30, BTCUSDT and ETHUSDT.
All 107 archives SHA256-verified against Binance's published digests, with
known market events located at their correct dates (see
`docs/bbma-backtest-results.md` for the landmark table). BTC and ETH only —
Binance lists no gold or GBP, so XAUUSD and GBPUSD remain on ~4 months.

**Two findings that change what the engine should be doing.**

## Results

| Strategy | Symbol | tf | Trades | TP1% | Gross | Net | Total |
|---|---|---|---|---|---|---|---|
| `sr_zone` (live) | BTCUSD | 15m | 7827 | 49.7% | +0.125R | **−0.319R** | −2495.4R |
| `sr_zone` (live) | ETHUSD | 15m | 8330 | 47.9% | +0.100R | **−0.244R** | −2033.8R |
| `sr_limit` (paper) | BTCUSD | 1h | 2981 | 50.2% | +0.174R | **+0.114R** | +340.6R |
| `sr_limit` (paper) | ETHUSD | 1h | 3015 | 49.7% | +0.157R | **+0.111R** | +334.2R |
| `orb_rvol` (unmerged) | BTCUSD | 15m | 1151 | 32.0% | +0.119R | −0.181R | −208.8R |
| `orb_rvol` (unmerged) | ETHUSD | 15m | 1109 | 33.7% | +0.138R | −0.076R | −84.1R |

Pooled:

| Strategy | n | Tier | Gross | Net | t | 95% CI | Total | Verdict |
|---|---|---|---|---|---|---|---|---|
| `sr_zone` | 16157 | taker | +0.112R | **−0.280R** | −27.6 | [−0.300, −0.260] | **−4529R** | LOSING |
| `sr_limit` | 5996 | maker | +0.166R | **+0.113R** | +6.8 | [+0.080, +0.145] | **+675R** | PROFITABLE |
| `orb_rvol` | 2260 | taker | +0.128R | −0.130R | −3.3 | [−0.206, −0.054] | −293R | LOSING |

## Two methodology corrections that decide these numbers

**1. Strategies were replayed in the configuration they actually run in, not
the one `signals/backtest.py` registers.** Those disagree for `sr_zone`: the
registry has it at 1h with 4h confluence, but `TRADING_SESSIONS` pins it to the
**15m scalp session with no confluence**. The gap is not cosmetic — at 1h it
measures −0.060R, at its live 15m it measures −0.280R, nearly five times worse.
The registry was flattering the live strategy by testing a different one.

**2. The fee tier is a property of the strategy, not the symbol.** Every
market-entry detector here enters at a bar close and pays taker (~20bps).
`sr_limit` rests an order at a zone edge and earns maker (~4bps). Charging it
taker fees measures a strategy nobody would run, and that single choice flips
its verdict from −0.100R to +0.113R. `r_model.cost_r` now takes a `bps`
override for this; `MAKER_BPS` documents when it may be used.

### Independent corroboration

`sr_limit`'s own docstring records numbers measured earlier over 2–4 years:

```
15m  market  -0.359R      1h  market  -0.126R
15m  limit   -0.052R      1h  limit   +0.065R   <- the only positive one
```

This nine-year run, on a different data source and a different backtester,
independently produces **15m market −0.280R** and **1h limit +0.113R**. Same
signs, same order of magnitude, arrived at separately. That is meaningful
cross-validation of the method, not just of the strategies.

## What this means

### `sr_zone` — the engine is running a losing strategy live

`sr_zone` is pinned to the **live 15m scalp session** and delivers Telegram
signals today. Over nine years and 16,157 trades it loses **0.280R per trade**,
totalling **−4,529R**. The t-statistic of −27.6 leaves no room for sampling
doubt.

The mechanism is entirely cost. Gross it is **+0.112R — genuinely positive**.
The rules find something. But a 15m stop is tiny relative to price, so a 20bps
round trip costs **0.392R per trade**, and the edge disappears three times over.
This is not a bad strategy; it is a good strategy run at a timeframe and entry
style that cannot pay for itself.

**Recommendation: stop delivering `sr_zone` on the 15m scalp session.** That is
a live-behaviour change affecting Telegram output, so I have not made it — it
is your call, not mine. The two coherent options are to move the scalp session
to 1h (where the same rules cost far less in R) or to switch it to limit entry,
which is exactly what `sr_limit` already is.

### `sr_limit` — the strongest result in the repo, and it is only on paper

**+0.113R net over 5,996 trades, t = +6.8, +675R total.** Bigger sample and
bigger t-statistic than `bbma_reentry` (+0.120R over 905 trades, t = +2.8).

The one caveat is the one its own docstring already makes, and it is not small:
the backtest assumes **you were filled**. It only emits a setup on a bar that
has already traded through the level, so the price is realistic — but queue
position and competition at an obvious level cannot be measured from candles at
all. The maker tier is what makes this strategy profitable, and the maker tier
is exactly what you forfeit if you do not get filled.

That is precisely what a paper trial exists to settle, and `PAPER_SR_LIMIT`
already implements it. **Recommendation: turn it on** (it is off by default)
and compare recorded fills against the backtest.

### `orb_rvol` — losing, and not on this branch

−0.130R net over 2,260 trades. Note its 32% TP1 rate against a 2R first target:
the wide ladder is deliberate, and the source paper's edge came from
cross-sectional selection across ~7,000 stocks, which two crypto symbols cannot
reproduce. The `orb_rvol` spec said this explicitly. The nine-year number
confirms it.

Its source lives only on the unmerged branch `feat/orb-rvol-strategy`
(`11dd40a`). It was extracted temporarily to produce this row and **not**
committed here, so `scripts/history_sweep.py` reports it as unavailable on this
branch rather than silently skipping it.

## Caveats applying to every row

- **Crypto only, two correlated symbols.** BTC and ETH move together, so the
  confidence intervals are narrower than the true independent-sample intervals.
- **Costs dominate at low timeframes.** Every verdict here is a statement about
  a fee tier as much as about a rule set. Confirm your actual tier in
  `r_model.COST_BPS` before acting on any of it.
- **Fills are assumed.** For market entries that is nearly free; for `sr_limit`
  it is the whole question.

## Follow-ups

1. Decide the `sr_zone` scalp-session question above — the largest single
   number in this document.
2. Turn on `PAPER_SR_LIMIT` to test the fill assumption forward.
3. `ema_cross`, `ict_smc`, `ict_fvg` and `ce_lwma` have still never been
   measured over long history. `scripts/history_sweep.py` takes them by adding
   one row each to `STRATEGIES`; `ce_lwma` needs multi-timeframe support the
   windowed replay does not yet have.
