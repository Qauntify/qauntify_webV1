# orb_rvol backtest results

```bash
.venv/bin/python -m scripts.orb_rvol_report
```

Run 2026-08-17 (UTC). Data: Binance monthly archives, **8.96 years**, BTCUSDT and
ETHUSDT, 15m, 313,438 bars per symbol. Provenance: every monthly archive is
individually SHA256-verified against Binance's published digest at download
time (`signals/analysis/history.py:download_month`) — the same mechanism
`scripts/history_provenance.py` exercises. This run did not additionally
re-run that script's historical-landmark cross-check (it defaults to 1h data,
a separate download this report doesn't use, and would have doubled the
download for a check that doesn't depend on interval — if a month's data
survives checksum verification, its authenticity doesn't change between 1h
and 15m granularity of the same underlying trades). The checksum guarantee
alone is enforced unconditionally; nothing here is unverified.

Scored under the corrected fixed-stop R model (`docs/r-model-correction.md`):
one third booked at each of TP1/TP2/TP3, the published stop never moves, so
an unbooked remainder loses its full share when the stop is hit.

## Headline

**`orb_rvol` is not profitable, and not close.** Net expectancy is negative on
both symbols, and the pooled result is one of the more statistically decisive
losses measured in this repository.

| Symbol | Years | Bars | Trades | TP1% | TP3% | Gross | **Net** | Total |
|---|---|---|---|---|---|---|---|---|
| BTCUSD | 8.96 | 313,438 | 1,226 | 31.9% | 13.7% | +0.051R | **−0.253R** | −309.8R |
| ETHUSD | 8.96 | 313,438 | 1,214 | 33.7% | 10.7% | −0.004R | **−0.224R** | −271.7R |

Pooled:

| n | Gross | **Net** | sd | t | 95% CI | Total |
|---|---|---|---|---|---|---|
| 2,440 | +0.024R | **−0.238R** | 1.709 | **−6.89** | **[−0.306, −0.170]** | −581.5R |

**t = −6.89.** For scale, every other strategy measured in this repository
sits between t = −1.24 (`cloud_mss`) and t = +2.77 (`bbma_reentry`, the one
genuine winner). This is not a borderline read — the 95% CI is nowhere near
zero, and at 2,440 trades the sample is large enough that "too small to
tell" isn't available as an explanation.

## Reading the result

Gross is roughly flat (+0.024R pooled — the relative-volume filter's raw
signal is close to a coin flip after direction and RVOL agree), and
round-trip transaction costs turn it decisively negative. This is exactly
the pattern documented for every other fast-timeframe strategy in this repo:

| Strategy | Timeframe | Net per trade | Verdict |
|---|---|---|---|
| `bbma_reentry` | 1h/4h | +0.120R | **profitable** (the one winner) |
| `sr_limit` (maker) | 1h | −0.015R | flat |
| `bbma_extreme` | 1h | −0.019R | losing |
| `cloud_mss` | 15m | −0.046R | losing |
| `bbma_extreme` | short sweep | −0.153R | losing |
| `bbma_reentry` | 15m-equivalent scope | −0.137R | losing |
| **`orb_rvol`** | **15m** | **−0.238R** | **losing badly** |
| `sr_zone` | 15m | −0.415R | losing badly |

`orb_rvol` lands in the worse half — better than `sr_zone` but clearly worse
than `cloud_mss`, and nowhere near `bbma_reentry`'s positive result at 1h/4h.
Six strategies have now been measured at 15m-or-faster over multi-year
history; none are profitable. The one profitable strategy in this repository
runs at 1h/4h specifically, for the same stated reason `orb_rvol` fails here:
wider stops make cost a smaller fraction of R.

### Why the SSRN paper's edge didn't transfer

This result is not a surprise relative to what the design spec
(`docs/superpowers/specs/2026-07-26-orb-rvol-strategy-design.md`) said going
in. The paper's entire edge came from the relative-volume filter applied
**cross-sectionally** — ranking the top 20 of ~7,000 stocks by RVOL each day
and trading only those. That selection mechanism needs a large universe to
work; with four instruments, RVOL here can only ever compare an instrument
against *its own* history, never against its peers on the same day. The spec
called this out explicitly before any code was written: *"What transfers is
the time-series half of the claim... The realistic goal is a
positive-expectancy, low-correlation addition to the existing five — not a
replacement for them."* The realistic goal was not met — but the caveat that
it might not be was on record before the measurement, which is the point of
measuring before shipping.

## What this means for delivery

**`orb_rvol` is not being promoted.** `TRADING_SESSIONS` remains unchanged —
no live session runs this strategy, and Telegram delivery behavior is
unaffected by any of this work.

It also remains admin-selectable in `bot_settings.signal_strategy` per Task
4 of the implementation plan, since that decision predates this result and
reverting it isn't necessary — the strategy simply won't be selected now that
the numbers are in. Worth flagging plainly, though: as currently wired, the
admin toggle wouldn't actually run this strategy correctly even if someone
selected it. Two gaps outside this measurement's scope:

1. `signals/pipeline/market_data.py`'s `EXTRA_HISTORY` has no entry for
   `orb_rvol`, so the live scan path fetches only `cfg.candle_limit` (200
   closed bars) — below `MIN_CANDLES = 400`, the detector's own floor. It
   would never produce a setup regardless of market conditions.
2. The admin toggle only controls the **swing** session, which runs on
   `1h` — not the `15m` this strategy's anchor/opening-range/RVOL-window
   arithmetic was designed and calibrated around. Feeding it 1h candles
   would silently reinterpret every time-based constant at 4x the intended
   scale (a 2-hour "opening range" instead of 30 minutes, a 16-hour trade
   window instead of 4, and the 13:30 UTC NY anchor never firing at all
   since it doesn't land on an hour boundary).

Given the result above, fixing either is not worth doing — there's nothing
to protect against by leaving it broken, but also nothing gained by making
it technically runnable. This is stated for the record, the same way
`cloud_mss`'s losing numbers are stated in its own results doc, rather than
silently left for a future reader to discover.

## Caveats

- **Crypto only.** Binance lists no gold or GBP, so `XAUUSD` and `GBPUSD`
  are not covered by this measurement. `signals/analysis/backtest.py`'s
  `fetch_extended_history` (added alongside this strategy) can pull a
  shorter, live-API-paginated sample for those two symbols via
  `python -m signals.analysis.backtest`, but at far less depth — not run as
  part of this report, and unlikely to change the verdict given how decisive
  the crypto result already is.
- **BTC and ETH are correlated.** The pooled 2,440-trade sample is not
  2,440 independent observations, so the true confidence interval is
  somewhat wider than reported — the same caveat `bbma_reentry`'s doc states.
  It does not change the direction of this result; a t-statistic of −6.89
  has substantial room to narrow and still be decisively negative.
- **No optimization was performed.** Every parameter (`OR_BARS`,
  `TRADE_WINDOW_BARS`, `RVOL_LOOKBACK`, `MIN_RVOL`, `ATR_STOP_BUFFER`,
  `MAX_STOP_ATR`, the 2R/4R/6R ladder) came from the design spec, fixed
  before this measurement ran. `git diff` over
  `signals/strategies/orb_rvol/` between the plan being written and this
  report running shows no parameter tuning.

## Follow-ups

1. **None planned for `orb_rvol` itself.** The result is decisive enough
   that further parameter sweeps would be curve-fitting against a strategy
   whose entire documented edge (the cross-sectional RVOL ranking) is
   structurally unavailable in this engine.
2. **The broader pattern continues to point at costs, not rules** — now six
   for six at 15m-or-faster. If a seventh strategy is ever considered for a
   fast timeframe, the prior from this repository's own evidence should be
   strongly negative unless there's a specific reason to expect this one's
   cost sensitivity differs.
