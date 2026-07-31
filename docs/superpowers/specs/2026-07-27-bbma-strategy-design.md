# BBMA (Bollinger Bands + Moving Average) — `bbma_extreme` and `bbma_reentry`

## Goal

Add the two most mechanizable setups from the BBMA Oma Ally playbook to the
pluggable strategy system, and measure them.

- `bbma_extreme` — mean reversion. A moving average escapes the Bollinger Band,
  price rejects back inside, and the trade fades the move.
- `bbma_reentry` — trend continuation. After a momentum leg, price pulls back
  into the MA5/MA10 zone, holds it, and the trade rejoins the trend.

Both are registered in the router and the backtester. **Neither is wired to a
live session and neither is admin-selectable by this work**: `TRADING_SESSIONS`,
`ADMIN_SELECTABLE_STRATEGIES` and the `bot_settings_signal_strategy_check`
migration are all untouched, so no Telegram behaviour changes. Promotion is
deferred until the backtest reports numbers — the same path `sr_zone` and
`orb_rvol` took.

## Research basis, and its limits

BBMA ("Bollinger Bands + Moving Average") is a retail forex system attributed to
Oma Ally, documented through community manuals, MT4/TradingView indicator
listings and forum threads rather than published research.

**There is no academic evidence base for BBMA.** Unlike `orb_rvol`, which is
anchored to Zarattini/Barbon/Aziz (SSRN 4729284) with bucketed per-trade
expectancy across ~7,000 stocks, nothing here has been independently tested. The
system as taught is also discretionary and multi-timeframe, so any mechanical
translation is an interpretation, not a faithful reproduction.

That is precisely why this spec stops at the backtest. The measurement is the
decision, not a formality.

### Indicator settings

Consistent across every source consulted:

| Indicator | Setting |
|---|---|
| Bollinger Bands | period 20, deviation 2, applied to Close → Upper / Mid / Lower |
| MA5 High / MA5 Low | **LWMA(5)** applied to highs / lows |
| MA10 High / MA10 Low | **LWMA(10)** applied to highs / lows |
| EMA50 | EMA(50) applied to Close |

The moving averages are *linear weighted*, not simple or exponential. `lwma()`
already exists in `signals/indicators.py`.

### The cycle

BBMA is taught as a loop, not a single entry:

```
Extreme → CSAK/CSD → Re-entry → CSM → Re-entry → … → MHV → Extreme
```

- **Extreme** — MA5-High escapes above Upper BB (sell) or MA5-Low below Lower BB
  (buy). A "CS Reverse" candle closes back inside the band, then a "CS Retest"
  candle retests MA5 and closes inside. Sources describe it explicitly as a
  scalp: take profit early, because direction is not yet confirmed. Targets at
  MA5/MA10, furthest at Mid BB.
- **CSM** (Candle Momentum) — a candle closing *outside* the band while the band
  is expanding. The band-state qualifier is the whole distinction: closing
  outside a **horizontal** band means reversion; outside a **vertical**
  (expanding) band means momentum.
- **Re-entry** — described everywhere as the safest entry. After a momentum leg,
  price pulls back into the MA5/MA10 zone: for a buy the low dips below MA5 but
  the close stays above MA10, and the close must not pass through the
  MA5/MA10/MidBB confluence.
- **MHV** ("Market Hilang Volume") — the band contracts, candles can no longer
  close outside it, often with a double top/bottom. Exhaustion.

### What is deliberately excluded

**CSM as an entry, and MHV/TPW entirely.** CSM's "expanding vs horizontal band"
test has no canonical threshold in any source — implementing it means inventing
a bandwidth number, which is a fitted parameter with nothing to fit against.
MHV depends on double-top and head-and-shoulders recognition that no source
defines mechanically. Both are excluded to keep the tested surface honest.

Momentum still appears in the design, but only in forms that need no invented
threshold — see the two notes under the detectors below.

## Architecture

```
signals/indicators.py            + bollinger(values, period=20, num_std=2.0)
signals/strategies/bbma/
  __init__.py                    exports detect_extreme, detect_reentry
  stack.py                       shared 5-line BBMA indicator stack + constants
  extreme.py                     mean-reversion detector
  reentry.py                     continuation detector
```

Two strategy keys, one package. The precedent is `sr_zone` / `sr_limit`: shared
detection code, separate keys, separate backtest rows.

Separate keys matter here for two concrete reasons. First, the patterns are
opposite in logic — one fades a move, the other follows it — so a single blended
expectancy could hide a profitable half behind a losing one. Second, they need
**different HTF confluence settings**, and confluence in `backtest.py` is keyed
per strategy: a trend filter that helps Re-entry would veto nearly every
Extreme.

### `bollinger` (new primitive)

Belongs in `signals/indicators.py` under that module's existing contract: a pure
function returning lists aligned 1:1 with the input, `None`-padded through the
warm-up window.

```python
def bollinger(values, period=20, num_std=2.0):
    """Bollinger Bands: (upper, mid, lower), each aligned to `values`.

    Mid is the simple moving average. The deviation is the POPULATION standard
    deviation over the same window, matching the MT4 / TradingView convention.
    """
```

Population σ (divide by `n`), not sample σ (`n-1`). This is the platform
convention BBMA practitioners' charts use, and the difference is material at
period 20.

### `stack.py`

Builds the canonical stack once from `candles`, reusing existing primitives:

```python
upper, mid, lower = bollinger(closes, 20, 2.0)
ma5h  = lwma(highs, 5)      ma5l  = lwma(lows, 5)
ma10h = lwma(highs, 10)     ma10l = lwma(lows, 10)
ema50 = ema(closes, 50)
```

Shared constants live here, not imported from `sr_zone`, so the two strategies
cannot drift into each other:

| Constant | Value | Meaning |
|---|---|---|
| `MIN_CANDLES` | 60 | EMA50 warm-up plus headroom |
| `STOP_ATR_BUFFER` | 0.5 | ATRs beyond the structural stop level |
| `MAX_STOP_ATR` | 2.5 | reject setups with a stop wider than this |

Both values match `sr_zone`'s conventions, which were arrived at on this
engine's own instruments.

## `bbma_extreme` — mean reversion

Signature matches `sr_zone`:
`detect_setup(symbol, candles, atr14, adx14=None, htf_trend=None)`.

Short (long is the mirror):

| # | Rule | Condition |
|---|---|---|
| 1 | MA5-High escaped above the band within the last `EXTREME_LOOKBACK` (6) bars | `any(ma5h[i] > upper[i])` |
| 2 | This bar closed back **inside** the band | `close < upper[-1]` |
| 3 | Retested MA5-High and was rejected | `high >= ma5h[-1] and close < ma5h[-1]` |
| 4 | Bearish close | `close < open` |

The escape window in rule 1 is `candles[-EXTREME_LOOKBACK:]` — it **includes the
current bar**, since the bar that rejects may itself be the one whose MA5 is
still outside the band.

- **Entry** — `bar.close`
- **Stop** — `max(c.high for c in candles[-EXTREME_LOOKBACK:]) + STOP_ATR_BUFFER × ATR`
  (long: `min(c.low ...) − STOP_ATR_BUFFER × ATR`)
- **Targets** — `EXTREME_TP1_R = 0.5`, `EXTREME_TP2_R = 1.0`,
  `EXTREME_TP3_R = 1.5`, declared in `extreme.py` (they are pattern-specific,
  unlike the shared constants in `stack.py`) and applied via
  `take_profits_from_risk(..., r1=, r2=, r3=)`

Long mirrors exactly: `ma5l[i] < lower[i]`, `close > lower[-1]`,
`low <= ma5l[-1] and close > ma5l[-1]`, `close > open`, stop below the lowest low.

### Why there is no band-expansion test

Rule 2 supplies BBMA's own momentum veto without inventing a parameter. The
doctrine states both halves directly: a candle closing outside an expanding band
is momentum and invalidates the Extreme, and "CS must close inside the BB" for
the Extreme to be valid. Requiring the close back inside the band therefore
excludes the momentum case by construction — **zero tuned parameters**.

### Why ADX and HTF trend are recorded but not gated

Extreme is counter-trend by construction; a trend filter would veto nearly all
of it. `adx14[-1]` and `htf_trend` are written into `indicators` for
diagnostics, and the detector does not branch on them. This is a deliberate
choice, not an omission, and the detector docstring must say so. Recording them
lets the backtest answer afterwards whether an ADX veto — the way `sr_zone` uses
`ADX_RANGE_MAX` — would have helped, instead of guessing now.

Consequently `CONFLUENCE_TIMEFRAMES` gets **no entry** for `bbma_extreme`.

## `bbma_reentry` — trend continuation

Same signature. Long (short is the mirror):

| # | Rule | Condition |
|---|---|---|
| 1 | Momentum leg — a candle closed outside the upper band within the last `MOMENTUM_LOOKBACK` (10) bars | `any(close[i] > upper[i])` |
| 2 | Band rising, not horizontal | `mid[-1] > mid[-MOMENTUM_LOOKBACK]` |
| 3 | Trend anchor | `close > ema50[-1]` |
| 4 | Pulled back into the MA5 zone | `low <= ma5l[-1]` |
| 5 | Close held the MA10 / Mid BB confluence | `close >= ma10h[-1] and close > mid[-1]` |
| 6 | HTF gate | reject if `htf_trend == "down"` |

The momentum-leg window in rule 1 is `candles[-MOMENTUM_LOOKBACK:-1]` — it
**excludes the current bar**. The current bar is the pullback that holds the MA
zone; a bar that is itself closing outside the band is the momentum candle, not
a re-entry into it.

- **Entry** — `bar.close`
- **Stop** — `min(bar.low, ma10l[-1]) − STOP_ATR_BUFFER × ATR`
- **Targets** — standard `TP1_R`/`TP2_R`/`TP3_R` = 1R / 2R / 3R

Short mirrors: `close[i] < lower[i]`, `mid[-1] < mid[-MOMENTUM_LOOKBACK]`,
`close < ema50[-1]`, `high >= ma5h[-1]`, `close <= ma10l[-1] and close < mid[-1]`,
reject if `htf_trend == "up"`, stop at `max(bar.high, ma10h[-1]) + buffer`.

Rules 4 and 5 are the sourced rule transcribed: "the low is below the MA5 and
the close is above the MA10", with the close not passing MA5/MA10/MidBB.

### Why Mid-BB slope stands in for band expansion

Rule 2 needs to express "the band is vertical, not horizontal" — the same
distinction CSM turns on. A bandwidth-expansion threshold would need a fitted
number. Mid-BB slope over the same lookback captures direction with no free
parameter, reusing a lookback the rule already has.

`CONFLUENCE_TIMEFRAMES["bbma_reentry"] = "4h"`, matching `sr_zone` and
`ict_smc`.

## Shared rejection guards

Both detectors reject when:

- `len(candles) < MIN_CANDLES`, or `atr14[-1]` is `None` or `<= 0`
- any required stack value at `[-1]` is `None` (warm-up)
- the stop is on the wrong side of entry (`stop >= entry` for a long)
- `abs(entry - stop) / atr > MAX_STOP_ATR`

Every emitted setup carries `indicators["strategy"]` set to `"bbma_extreme"` or
`"bbma_reentry"`, plus its band and MA values, so stored signals and the chart
plan can identify the pattern later.

## Registration

| File | Change |
|---|---|
| `signals/models.py` | add `"bbma_extreme"`, `"bbma_reentry"` to `SIGNAL_STRATEGIES` |
| `signals/strategies/router.py` | two dispatch branches, matching the `sr_zone` shape |
| `signals/strategies/__init__.py` | unchanged — exports the router's `detect_setup` |
| `signals/backtest.py` | `STRATEGY_TIMEFRAMES` + `CONFLUENCE_TIMEFRAMES` entries |

`TRADING_SESSIONS`, `AUXILIARY_SESSIONS`, `ADMIN_SELECTABLE_STRATEGIES` and the
Supabase migration are **not** touched. `tests/core/test_strategy_choices.py`
pins `ADMIN_SELECTABLE_STRATEGIES` against the migration and the web dropdown;
adding to `SIGNAL_STRATEGIES` alone keeps that pin satisfied.

**No chart builder.** `build_chart_plan` falls back to `_no_structure` for an
unregistered strategy, so annotated charts degrade to trade levels only rather
than breaking. A `_bbma` builder is deferred until a pattern earns a live slot.

## Data availability — measured

Backtest depth was measured, not assumed:

| Timeframe | BTC / ETH / GBP (Kraken) | XAUUSD (Yahoo) |
|---|---|---|
| 15m | 721 bars = **7.5 days** | 1831 bars = 28.6 days |
| 1h | 721 bars = **30 days** | 1434 bars = 91 days |
| 4h | 721 bars = **120 days** | 2829 bars, median gap **60 min** |

Two consequences:

**15m is not decision-grade** for the Kraken symbols. Kraken hard-caps OHLC at
721 bars regardless of the `limit` argument and does not serve deep history, so
pagination cannot extend it. 7.5 days yields single-digit trade counts. The
sweep therefore centres on **1h and 4h**, and the report prints trade counts so
a thin row is visibly thin.

**Gold's 4h series is not 4h.** `YAHOO_INTERVAL["4h"] = ("1h", "6mo")` in
`signals/market_client.py`, so `fetch_candles("XAUUSD", "4h")` returns hourly
candles — confirmed by a measured median gap of 60.0 minutes across 2,829 bars.

This is pre-existing and wider than BBMA: `backtest.py` uses 4h for HTF
confluence on every strategy, so XAUUSD's higher-timeframe trend in the current
backtest is computed from 1h data while being labelled 4h, for `ema_cross`,
`ict_smc` and `sr_zone` alike. `bbma_reentry` uses the same 4h confluence.

### Fix: resample gold to true 4h

In the gold path of `signals/market_client.py`, aggregate Yahoo's hourly series
into 4-hour buckets when `interval == "4h"`: group by floored 4h boundary, then
take first open, max high, min low, last close, summed volume. Buckets aligned
to the UTC epoch so they are reproducible.

This is contained to the gold branch, gives BBMA an honest 4h XAUUSD row, and
corrects the mislabelled 4h HTF confluence the existing strategies have been
using for gold. It needs its own test asserting the returned median gap is 240
minutes and that OHLC aggregation is correct.

## Backtest

### Net-of-cost R (addition to `backtest_strategy`)

`backtest_strategy` gains `stats["net_expectancy_r"]` and
`stats["net_total_r"]`, each trade's gross R reduced by
`r_model.cost_r(symbol, entry, stop)`. Additive keys only — no existing key
changes value, and no existing caller breaks.

This is not optional for BBMA. Extreme's TP1 sits at 0.5R of a deliberately
tight stop, and cost expressed in R scales inversely with stop distance — the
`r_model` docstring makes exactly this point, and it is what separated the
losing 15m `sr_limit` variant from the winning 1h one. A gross-only number would
flatter Extreme specifically.

`r_model` stays the single source of truth for both cost and R; nothing is
recomputed locally.

### `scripts/bbma_report.py`

A standalone sweep, following the `scripts/gate_report.py` and
`scripts/calibration_report.py` precedent rather than bending shared code:

- strategies: `bbma_extreme`, `bbma_reentry`
- symbols: `BTCUSD`, `ETHUSD`, `XAUUSD`, `GBPUSD`
- timeframes: `1h`, `4h`
- HTF confluence stepped one level up per row — `1h → 4h`, `4h → 1d` — applied
  only to `bbma_reentry`, since `bbma_extreme` is ungated by design
- columns: `trades`, `tp1%`, `tp3%`, `gross exp-R`, `net exp-R`, `total-R`

The script needs its own timeframe-minutes map including `"1d": 1440`;
`backtest.py`'s `TF_MINUTES` currently stops at `4h`.

`signals/backtest.py`'s own `main()` also gains the two BBMA entries so
`python -m signals.backtest` covers them at their default timeframe
(`bbma_extreme` → 1h, `bbma_reentry` → 1h).

### How to read the result

A pattern is worth promoting only if it clears **positive net expectancy** with
a trade count large enough to mean anything, on more than one symbol. Given the
depth limits above, a plausible outcome is that neither reaches that bar on the
available history — that is a real answer, and the spec commits to reporting it
as one rather than promoting on a gross number or a thin sample.

## Testing

`tests/strategies/test_bbma_detector.py`, synthetic series in the style of
`tests/strategies/test_sr_limit_detector.py`:

**Extreme**
- fires short on a valid escape → close-inside → MA5 retest-and-reject sequence
- fires long on the mirror
- no setup when MA5 never escaped the band
- no setup when the current bar closes *outside* the band (the momentum veto)
- no setup when the bar closes beyond MA5 rather than rejecting from it
- stop sits beyond the escape-window extreme by `STOP_ATR_BUFFER × ATR`
- targets resolve to 0.5R / 1R / 1.5R
- rejects when the resulting stop exceeds `MAX_STOP_ATR`
- `htf_trend="down"` does **not** suppress a long (pins the deliberate no-gate)

**Re-entry**
- fires long on momentum leg → rising mid → EMA50 above → MA5 pullback → MA10 hold
- fires short on the mirror
- no setup without a prior close outside the band
- no setup when the Mid BB is flat or falling
- no setup when the close breaks below the Mid BB
- no setup when the close is below MA10-High
- `htf_trend="down"` vetoes a long; `"up"` vetoes a short
- targets resolve to 1R / 2R / 3R

**Indicators** — a known-value test for `bollinger` on a hand-computed series,
asserting population σ, correct alignment and `None` padding.

**Market client** — gold 4h resample returns 240-minute spacing and correct
first-open / max-high / min-low / last-close / summed-volume aggregation.

## Out of scope

- CSM as an entry, MHV, TPW, EMA50-gap and Rejection setups
- Live session assignment (`TRADING_SESSIONS` unchanged)
- Admin selectability, the Supabase constraint migration, and the web dropdown
- A `_bbma` chart-plan builder
- Multi-timeframe BBMA as taught (H4 bias → H1 setup → M15 entry); both
  detectors read one timeframe plus the existing HTF trend gate
- Deep history beyond what `market_client` serves; the HuggingFace XAUUSD
  dataset under `ml/data/` is XAUUSD-only and belongs to the ML tree, which is
  not wired into the live engine
