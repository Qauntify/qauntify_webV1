# Session Opening Range Breakout on Relative Volume (`orb_rvol`)

## Goal

Add a session Opening Range Breakout playbook to the pluggable strategy system.
At each major session open (00:00 / 07:00 / 13:30 UTC) mark the first 30 minutes
as an opening range, then trade the first breakout **in the direction the
opening range itself moved** — but only when that opening range traded on
abnormally high volume relative to the same session's own recent history.

Admin-selectable. **Not** assigned to a live trading session by this work:
`TRADING_SESSIONS` is unchanged, so no Telegram signal behaviour changes. The
decision to promote it to a session slot is deferred until the backtest reports
numbers, matching how `sr_zone` earned the scalp slot.

## Research basis

Primary source: Carlo Zarattini, Andrea Barbon, Andrew Aziz, *A Profitable Day
Trading Strategy For The U.S. Equity Market* (SSRN 4729284) — ~7,000 US stocks,
2016–2023, free of survivorship bias.

The paper's central result is a **contrast**, and it is the reason this strategy
is worth adding at all:

| Variant | IRR | Sharpe | Hit ratio | MDD | Alpha |
|---|---|---|---|---|---|
| ORB base (all stocks) | 3.2% | 0.48 | 41.4% | 13% | 3.3% |
| ORB + Relative Volume | 41.6% | 2.81 | 48.4% | 12% | 35.8% |
| S&P 500 buy & hold | 14.2% | 0.78 | 54.9% | 34% | — |

Plain ORB **underperformed buy-and-hold**. The entire edge came from the
relative-volume filter. Their bucketed per-trade expectancy is monotonic in
RVOL, which is what a real effect looks like rather than a fitted one:

| Opening-range RVOL | Avg PnL per trade |
|---|---|
| < 100% | −0.02R |
| > 100% | +0.08R |
| > 30x | +0.38R |

Supporting findings the design leans on:

- Direction is taken from the opening range candle and **not** overridden: a
  bearish opening range permits only shorts, a bullish one only longs, a doji
  no trade.
- Tsai et al. (2018): profits concentrate when the opening range is short
  relative to the session.
- Lundström (2017): ORB profitability grows with underlying volatility.
- The authors attribute robustness to "minimal parameters based on economic
  rationale rather than retrospective optimization" — so this design
  deliberately adds no gates beyond those the evidence supports.

### What does not transfer, and why

The paper trades the **top 20 of ~7,000 stocks by RVOL each day**. That
cross-sectional selection across a large universe, driven by stock-specific
catalysts (earnings, FDA rulings, M&A), is structurally unavailable with four
instruments. The 2.81 Sharpe is therefore **not** a forecast for this engine.

What transfers is the time-series half of the claim: *only take the breakout
when this instrument is unusually active right now*. The realistic goal is a
positive-expectancy, low-correlation addition to the existing five — not a
replacement for them.

## Detector contract

`signals/strategies/orb_rvol/detector.py`

```
detect_setup(symbol, candles, atr14, adx14=None, htf_trend=None) -> CandidateSetup | None
```

Same signature as `sr_zone`, so router wiring is uniform. Timeframe: **15m**.

This is the first detector in the codebase to read `Candle.volume` — every
existing detector ignores it — and the first to be time-of-day aware.

### Session anchors

```
SESSION_ANCHORS_UTC = ((0, 0, "Asia"), (7, 0, "London"), (13, 30, "NY"))
```

All three fall on 15m boundaries. Opening range = the first `OR_BARS = 2` closed
candles after an anchor (30 minutes). Trade windows are
`TRADE_WINDOW_BARS = 16` (4 hours) after the OR closes, which by construction
**cannot overlap the next anchor**:

| Anchor | OR closes | Window ends | Next anchor |
|---|---|---|---|
| 00:00 | 00:30 | 04:30 | 07:00 |
| 07:00 | 07:30 | 11:30 | 13:30 |
| 13:30 | 14:00 | 18:00 | 00:00 |

### Relative volume

```
RVOL = OR_volume(current anchor) / mean(OR_volume over the previous N same-anchor opens)
```

Comparing against **the same anchor's** history rather than a rolling average is
a necessary adaptation, not a stylistic one. Volume at 13:30 UTC is
structurally many times volume at 00:00 UTC, so a rolling mean would flag every
NY open as "abnormal" and every Asia open as "quiet" — measuring time-of-day
seasonality instead of the catalyst the paper actually detects.

Requires at least `MIN_RVOL_SAMPLES` prior same-anchor opens; fewer → no trade.
Zero-volume bars occur in the gold feed (`market_client` falls back to `0.0`
when Yahoo omits a bar's volume), so a prior open whose OR volume is 0 is
excluded from the mean, and a **current** OR volume of 0 returns no setup.

### Algorithm

1. Guard: `len(candles) >= MIN_CANDLES` (~4 days of 15m, so at least
   `MIN_RVOL_SAMPLES` prior opens exist for every anchor),
   `atr14[-1] is not None`, `atr > 0`.
2. Locate the anchor whose trade window contains the latest closed bar. None →
   return None.
3. Slice that anchor's OR bars. Incomplete (fewer than `OR_BARS`) → None.
4. `or_high = max(highs)`, `or_low = min(lows)`,
   `or_direction = sign(last OR bar close − first OR bar open)`. Doji
   (`close == open`) → None.
5. Compute RVOL from the previous `RVOL_LOOKBACK` same-anchor opens. Below
   `MIN_RVOL` or insufficient samples → None.
6. The latest closed bar must be the **first** bar in the trade window to close
   beyond the OR edge in the OR's direction — long requires
   `close > or_high` with a bullish OR, short `close < or_low` with a bearish
   OR. Any earlier bar in the window having already closed beyond that edge →
   None (one trade per anchor; the detector is stateless, so "first" is
   re-derived from the window each call).
7. `entry = bar.close` (engine convention).
   `stop = or_low − ATR_STOP_BUFFER * atr` for longs,
   `or_high + ATR_STOP_BUFFER * atr` for shorts.
8. Risk: reject stops wider than `MAX_STOP_ATR * atr`, and reject a stop on the
   wrong side of entry. Targets **2R/4R/6R** via
   `take_profits_from_risk(entry, stop, direction, r1=2.0, r2=4.0, r3=6.0)`.
9. `indicators`: `strategy="orb_rvol"`, `session` ("Asia"/"London"/"NY"),
   `or_high`, `or_low`, `or_direction` ("bullish"/"bearish"), `rvol`, `atr`,
   `anchor_time`, plus `adx` / `htf_trend` when supplied.

### Deliberate omissions

- **`htf_trend` is recorded but never vetoes.** The opening range *is* the
  directional thesis; the paper applies no higher-timeframe filter. Adding one
  is unresearched and would roughly halve an already-thin trade count. It stays
  in `indicators` for the LLM, charts and later A/B testing.
- **`adx` is recorded but never gates.** Same reasoning.
- **No minimum opening-range width.** Tempting, but unsupported by the source
  and a straight path to overfitting.

### Adapted from the paper

- **Stop.** The paper uses 10% of the *daily* ATR. `atr14` here is computed on
  the 15m trading timeframe, so 10% of it would sit inside the spread and stop
  out on noise. The opposite edge of the opening range plus an ATR buffer is
  the standard structural equivalent.
- **Targets.** The paper uses no profit target and exits at the session close,
  citing Wu et al. (2020) that targets are detrimental. The engine's outcome
  tracker, charts and track-record page are all built on TP1/TP2/TP3, so the
  ladder is kept but widened to 2R/4R/6R (vs the 1R/2R/3R default and
  `super_scalp`'s 0.5R/1R/1.5R) to leave room for the runners the edge depends
  on.
- **Time exit.** No intraday time-based exit exists in the outcome tracker;
  positions expire via the session's `max_open_days`. The 4-hour trade window
  constrains *entry*, not exit.

### Parameters (initial)

| Name | Value | Meaning |
|---|---|---|
| `OR_BARS` | 2 | 15m bars forming the opening range (30 min) |
| `TRADE_WINDOW_BARS` | 16 | bars after OR close in which a breakout may trigger |
| `RVOL_LOOKBACK` | 10 | prior same-anchor opens averaged |
| `MIN_RVOL_SAMPLES` | 3 | minimum priors before RVOL is trusted |
| `MIN_RVOL` | 1.0 | paper's threshold (expectancy flips sign here) |
| `ATR_STOP_BUFFER` | 0.25 | stop distance beyond the OR edge |
| `MAX_STOP_ATR` | 2.5 | reject wide stops (matches `sr_zone`) |
| `MIN_CANDLES` | 400 | ~4.2 days of 15m; 3 days would only just reach `MIN_RVOL_SAMPLES` |
| `TP_R` | 2.0 / 4.0 / 6.0 | wide ladder for a runner strategy |

## File layout

```
signals/strategies/orb_rvol/
  __init__.py    # re-export detect_setup (mirrors ict_fvg)
  windows.py     # anchor detection, OR slicing, relative volume
  detector.py    # entry / stop / TP rules
```

Split two ways because the window-and-volume arithmetic is the fiddly part and
is worth testing independently of the setup rules.

## Integration (mirrors `sr_zone` wiring)

| File | Change |
|---|---|
| `signals/strategies/orb_rvol/` | new `windows.py`, `detector.py`, `__init__.py` |
| `strategies/router.py` | dispatch `orb_rvol` |
| `models.py` | add `"orb_rvol"` to `SIGNAL_STRATEGIES`; `TRADING_SESSIONS` unchanged |
| `run.py` | add to the `_no_setup_indicators` strategy tuple |
| `composer.py` | no-setup reason, indicator formatting, strategy line |
| `rag/playbook.py` | confirm-gate + reject-cues chunks |
| `backtest.py` | `STRATEGY_TIMEFRAMES["orb_rvol"] = "15m"`; extended history helper |
| `web/src/lib/supabase/admin.ts` | add to the admin dropdown |
| `tests/strategies/test_orb_rvol_detector.py` | new |

No confluence timeframe is registered in `CONFLUENCE_TIMEFRAMES`, so the
backtest passes `htf_trend=None` — consistent with the detector not gating on
it.

## Extended backtest history

`DEFAULT_CANDLE_LIMIT = 720` on 15m is 7.5 days ≈ 22 session opens per symbol,
and RVOL cannot compute until `MIN_RVOL_SAMPLES` priors exist — leaving roughly
a dozen tradeable opens per symbol. That is too thin to decide anything, which
would defeat the "backtest first, then promote" plan.

`fetch_candles` already accepts `start_time` (epoch ms) and filters forward from
it, so `backtest.py` gains a helper that pages forward from
`now − total * interval` in provider-sized chunks, using each batch's last
`open_time` as the next `start_time`, de-duplicating and stopping when a batch
returns no new bars. Target ~3,000 15m bars (~31 days, ~90 opens/symbol).

Bounded by provider limits: Kraken returns at most ~720 OHLC bars per `since`
request, and Yahoo caps intraday history (gold is fetched from Yahoo). The
helper takes what is available rather than failing.

## Testing

TDD, with synthetic candle series as the other detector tests do. A helper
builds a series on 15m boundaries anchored to a known UTC timestamp so anchors
land deterministically.

`windows.py`:
- anchor detection at each of 00:00 / 07:00 / 13:30, and None mid-window
- OR slicing returns exactly `OR_BARS`; incomplete range → None
- RVOL averages only same-anchor priors, not neighbouring sessions
- fewer than `MIN_RVOL_SAMPLES` priors → None
- zero-volume priors excluded from the mean; zero current OR volume → None

`detector.py`:
- bullish OR + high RVOL + first close above `or_high` → long, stop below
  `or_low`, targets at 2R/4R/6R
- bearish OR mirror → short
- RVOL below `MIN_RVOL` → None (the headline gate)
- bullish OR but price breaks *down* through `or_low` → None (direction lock)
- doji OR → None
- a second breakout bar in the same window → None (one trade per anchor)
- breakout after the trade window closes → None
- stop wider than `MAX_STOP_ATR` → None
- router dispatch for `"orb_rvol"`

## Out of scope

- Assigning `orb_rvol` to a live `TRADING_SESSIONS` slot (deferred to the
  backtest result).
- Intraday time-based exit at session close (needs outcome-tracker changes).
- Cross-sectional "trade only the top-N most active symbols today" ranking —
  the part of the paper that needs a large universe. Could be revisited if the
  symbol list grows substantially.
- A/B testing an `htf_trend` veto variant.
