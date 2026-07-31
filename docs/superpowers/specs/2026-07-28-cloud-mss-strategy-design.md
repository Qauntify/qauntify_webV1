# Cloud + Market Structure Shift (`cloud_mss`)

## Goal

Trade the 15m chart off the "cloud" drawn by `strategy_doc/TrendFollowingClaud.pine`
— the band between a 1h Chandelier Exit and a 15m LWMA200 — entering when price
pulls back into the cloud, is rejected, and then confirms with a change of
character in the trade direction.

The cloud is a dynamic support/resistance zone whose side sets the bias:

- **Premium** — the cloud sits above price. A rally into it is a **sell**.
- **Discount** — the cloud sits below price. A drop into it is a **buy**.

This replaces `sr_zone` on the 15m session. It is not additive: the unique
index `signals_one_open_per_symbol_tf` covers `(symbol, timeframe)` for open
signals, so two strategies scanning 15m would collide on the same symbol and
one insert would fail. Replacing also retires the stream measured at −0.415R
per trade over 8.87 years.

## Source

`strategy_doc/TrendFollowingClaud.pine`, a Pine v6 indicator. The parts this
design uses:

| Pine | Setting | Line |
|---|---|---|
| Chandelier Exit 1 | timeframe 60, ATR 22, multiplier 4.5, lookback 22 | 7–11 |
| Moving average | timeframe 15, LWMA, period 200, on close | 25–28 |
| Cloud | `fill(ce1FillAnchor, maPlot, ...)` — CE1 band to MA | 226 |
| Internal structure | pivot length 5 | 300 |

Everything else in the file — Bollinger Bands, session boxes, the ATR
dashboard, the watermark, CE2 — is display and is **not** part of this
strategy.

### The ATR discrepancy, and why it is being fixed

The Pine computes ATR as `ta.sma(ta.tr(true), length)` and comments that this
is deliberate: *"MT5 iATR is a simple average of True Range, not Wilder
smoothing"* (line 154–155). `signals/indicators.py::atr` is Wilder-smoothed,
and `chandelier_exit` uses it.

The two put the Chandelier bands in different places, so a cloud drawn by the
engine would not match the cloud on the chart being read. A setup verified by
eye would not be the setup that fired. This design adds the MT5 variant rather
than accepting that gap.

`ce_lwma` keeps Wilder and is untouched — it was built against the Wilder
version and its behaviour must not shift silently.

## Rules

All values are read on the **last closed** 15m bar unless stated.

### The cloud

```
ce_band  = active Chandelier Exit band on 1h    (long stop when bullish,
                                                 short stop when bearish)
ma200    = lwma(15m closes, 200)
cloud_low  = min(ce_band, ma200)
cloud_high = max(ce_band, ma200)
```

### Bias

| Bias | Condition |
|---|---|
| Premium (sell) | 1h CE trend is bearish **and** `close < cloud_low` |
| Discount (buy) | 1h CE trend is bullish **and** `close > cloud_high` |

Requiring price to sit fully outside the cloud is what makes the next step a
*pullback into* the zone rather than a reading taken mid-traverse.

### 1. Touch

Within the last `TOUCH_LOOKBACK` (6) bars, a bar wicked into the cloud and
closed back out of it:

- Sell: `high >= cloud_low` **and** `close < cloud_low`
- Buy: `low <= cloud_high` **and** `close > cloud_high`

Closing back out is the rejection. A bar that closes inside the cloud has not
been rejected by it yet, and one that closes through has invalidated it.

### 2. CHoCH

After the touch bar and within `MAX_BARS_SINCE_TOUCH` (4) bars, a close breaks
the most recent opposing pivot formed **before** the touch:

- Sell: close below the most recent swing low
- Buy: close above the most recent swing high

Pivots use `pivot_highs`/`pivot_lows` from `ict_smc.detector` with
`left = right = STRUCTURE_PIVOT` (2, the module's existing setting — see
"Pivot width" below).

**What makes this a CHoCH and not a BOS**, stated mechanically because the
distinction is the whole confirmation and prose will not survive translation
into code:

The move into the cloud is a leg — for a sell, a rally making higher highs.
The break that confirms must run *against* that leg.

- Qualifies (sell): a close **below** the most recent swing low formed before
  the touch bar. The rally has given up its own structure — a change of
  character.
- Voids the setup (sell): a close **above** the most recent swing high formed
  before the touch bar, at any bar between the touch and the CHoCH. That is the
  pullback resolving as continuation *through* the cloud, not a turn at it. The
  setup is dead, not merely unconfirmed, and must not fire if price later dips
  back below the swing low.

Buy is the mirror: a close above the pre-touch swing high qualifies, and a
close below the pre-touch swing low voids.

Without the void rule a detector would happily wait out a breakout and then
fire on the first pullback, which is a different trade entirely.

### 3. Entry

Entry is the close of the CHoCH bar — the bar that completes the sequence.

### Risk

| | Sell | Buy |
|---|---|---|
| Entry | CHoCH bar close | CHoCH bar close |
| Stop | `cloud_high + STOP_ATR_BUFFER · atr14` | `cloud_low − STOP_ATR_BUFFER · atr14` |
| Targets | 1R / 2R / 3R | 1R / 2R / 3R |

The cloud is the invalidation zone: a clean close through it means the read was
wrong, so the stop sits past its far edge. `STOP_ATR_BUFFER` is 0.5 and
`MAX_STOP_ATR` is 2.5, matching `sr_zone` and the BBMA stack.

Targets stay on the engine's R ladder so expectancy is directly comparable with
every other strategy under the corrected fixed-stop R model
(`docs/r-model-correction.md`).

### Rejection guards

- fewer than `MIN_CANDLES` (230) 15m bars, or no 1h candles
- `atr14[-1]` missing or non-positive
- CE trend or MA200 still warming up (`None`)
- stop on the wrong side of entry
- `abs(entry − stop) / atr > MAX_STOP_ATR`

### Pivot width

`ict_smc` uses `PIVOT_LEFT = PIVOT_RIGHT = 2`; the Pine's internal structure
uses length 5. They are different formulations — the Pine's `structureLeg`
tracks leg changes against a rolling extreme, while `pivot_highs` requires a
bar to be the extreme of a symmetric window — so the numbers are not
comparable and 5 is not simply "stricter".

This design reuses `ict_smc`'s pivots at their existing width rather than
reimplementing the Pine's leg tracker. Reason: it is already tested and already
used by a live strategy, and inventing a second pivot definition to chase a
number that does not transfer would add a knob with nothing to tune it
against. Recorded as a deliberate divergence, not an oversight.

## Architecture

| File | Change |
|---|---|
| `signals/indicators.py` | add `sma_atr(highs, lows, closes, period)`; `chandelier_exit` takes `atr_fn=atr` |
| `signals/strategies/cloud_mss/__init__.py` | export `detect_setup` |
| `signals/strategies/cloud_mss/detector.py` | the strategy |
| `signals/strategies/router.py` | dispatch, passing `h1_candles` |
| `signals/models.py` | `SIGNAL_STRATEGIES`; 15m session strategy `sr_zone` → `cloud_mss` |
| `signals/run.py` | `_load_market_data` fetches 1h + raises the candle limit for `cloud_mss` as it does for `ce_lwma` |
| `signals/backtest.py` | `backtest_windowed` gains an aligned HTF candle series |
| `signals/chart/plan.py` | `_cloud_mss` builder — cloud zone, MA200, CE band, CHoCH level |

`chandelier_exit` gaining an `atr_fn` parameter defaulting to the current `atr`
keeps every existing caller byte-identical in behaviour while letting this
strategy pass `sma_atr`.

### Multi-timeframe data

The router already carries `h1_candles` for `ce_lwma`, and `_load_market_data`
already fetches 1h and raises the candle limit when the strategy is `ce_lwma`.
Both branches extend to `cloud_mss` rather than growing a second fetch path.

The limit for `cloud_mss` is `max(cfg.candle_limit, 260)`, **not** the 220 that
`ce_lwma` uses. `_load_market_data` drops the still-forming bar, so a 220-bar
fetch yields 219 closed bars — and `MIN_CANDLES` of 230 would then never be
met, leaving a detector that silently never fires. 260 yields 259 closed bars:
200 for the LWMA warm-up plus ~30 for the structure and touch lookbacks, with
room to spare. The relationship is `fetch − 1 > MIN_CANDLES`, and a test pins
it so the two constants cannot drift apart.

## Backtesting — the real work

**The harness does not support multi-timeframe strategies.** `backtest.py`
states it: *"no multi-timeframe strategies (ce_lwma needs H1 alignment — not
covered here)"*. `backtest_windowed` passes
`(symbol, candles, atr14, htf_trend=...)` and has nowhere to put 1h candles.

`backtest_windowed` gains an optional `htf_candles` parameter. For each primary
bar it passes the slice of higher-timeframe candles that had **closed** by that
bar's open time — the same causality rule `htf_trend_series` already applies,
handing over candles instead of a trend string. A bar must never see a 1h
candle that had not finished forming.

Alignment is computed once with a forward-walking index, as `htf_trend_series`
does, not re-scanned per bar.

This is not optional. After `docs/r-model-correction.md` no strategy goes into
a live session unmeasured, and this one cannot be measured at all until the
harness can feed it. It also unblocks `ce_lwma`, live on no session today and
never measured over long history.

Measurement runs over the verified Binance archives (`signals/history.py`),
BTC and ETH, 15m primary with 1h for the cloud.

## Testing

`tests/strategies/test_cloud_mss_detector.py` — rules, on synthetic series:

- fires short on premium: cloud overhead, wick into it, close back below, then
  a close under the prior swing low
- fires long on the discount mirror
- no setup when price is inside the cloud (no pullback happened)
- no setup when the touch bar closes *inside* the cloud (not rejected)
- no setup when the touch bar closes *through* the cloud (invalidated)
- no setup when the CE trend disagrees with the cloud side
- no setup without a CHoCH after the touch
- no setup when a close breaks the pre-touch swing high before the CHoCH (a
  breakout through the cloud voids the setup, and it must stay void even if
  price later closes below the pre-touch swing low)
- no setup when the CHoCH arrives more than `MAX_BARS_SINCE_TOUCH` bars later
- stop sits past the cloud's far edge by `STOP_ATR_BUFFER · atr`
- targets resolve to 1R/2R/3R
- rejects when the stop exceeds `MAX_STOP_ATR`
- returns `None` when `h1_candles` is empty or too short
- `MIN_CANDLES` is strictly less than the closed-bar count the fetch yields, so
  the detector cannot be starved by its own candle limit

`tests/core/test_indicators.py`:

- `sma_atr` equals a plain mean of true range over the window, and differs from
  Wilder `atr` on the same series
- `chandelier_exit` with `atr_fn=sma_atr` produces different bands than the
  default, and the default path is unchanged

`tests/core/test_backtest.py`:

- `backtest_windowed` passes only HTF candles closed at or before the primary
  bar's open time
- an empty HTF series yields no setups rather than raising

`tests/core/test_pipeline.py`:

- the 15m session's strategy is `cloud_mss`
- `_load_market_data` fetches 1h candles for it

## Out of scope

- Everything in the Pine that is display only: Bollinger Bands, session boxes
  and liquidity rays, the ATR dashboard, the watermark, CE2, the legend
- The Pine's own `structureLeg` pivot formulation (see "Pivot width")
- Swing structure (length 50) as an alternative confirmation
- Admin selectability and its migration — this is a pinned session strategy,
  which does not read `bot_settings.signal_strategy`
- GBPUSD, which `SESSION_SYMBOLS` restricts to the swing session and which
  therefore will not receive this strategy
- Promotion on faith: if the backtest says this loses, it does not ship
