# Scalp Session: 5m Price-Action Strategy (S/R Bounce)

## Problem

The scalp session currently trades 15m candles using the same indicator-based
EMA9/21 crossover strategy as swing (`ema_cross`), gated by a 1h EMA
confluence filter. The user wants scalp to instead trade 5m candles using a
pure price-action strategy — no EMA/RSI/MACD/ADX — while swing stays exactly
as it is today (1h, `ema_cross`, no confluence).

Strategy selection is also currently a single global admin setting
(`bot_settings.signal_strategy`) applied to both sessions via
`signals/strategies/router.py`. Since scalp and swing now need to run
permanently different strategies, that global setting no longer makes sense.

## Decisions

- **Scalp timeframe**: `15m` → `5m`. `max_open_days` stays `2`.
- **Scalp strategy**: new `sr_bounce` detector — support/resistance bounce,
  pure price action.
- **Swing**: unchanged in every respect (`1h`, `ema_cross`, no confluence,
  14-day expiry).
- **Strategy is hardcoded per session, not admin-configurable.** Each
  `TradingSession` carries its own `strategy` field; `router.py` dispatches
  on that instead of `bot_settings.signal_strategy`. The "Signal strategy"
  dropdown is removed from Admin → AI Settings. `bot_settings.signal_strategy`
  stops being read/written by the app code; the column is left in place in
  Supabase (no destructive migration).
- **S/R level qualification**: a level (built from clustered swing
  highs/lows) only becomes tradeable once **at least 2 pivots** land within
  tolerance of each other — a single untested swing point doesn't count.
- **Entry trigger**: "simple close-back-through" — once a level is
  qualified, the next candle that touches/pierces it and closes back on the
  correct side fires the signal. No wick-shape (pin-bar) requirement.
- **Stop/target math matches the existing strategies**: stop = trigger
  candle's low/high ∓ `0.5 × ATR14`, target = `entry ± 2.0 × risk` (fixed
  2:1 R:R). ATR is used only to size the stop distance, not to decide
  direction — it doesn't reintroduce "indicator-based" entries.
- **Scalp's 1h confluence filter is replaced, not dropped**: instead of the
  EMA9/21-based higher-timeframe trend used today, scalp gates on a
  **structure-based** 1h bias (rising/falling swing highs and lows). Same
  fail-open semantics as today (`None` bias doesn't block a setup).
- **No ADX / trend-strength filter on `sr_bounce`.** ADX≥20 makes sense for
  a trend-following crossover; a reversal/bounce strategy gating on "market
  is trending" would work against its own premise. `sr_bounce` has zero
  traditional indicators in its entry logic — ATR (stop sizing) and the
  structure-based HTF bias are the only non-pure-candle inputs.
- **Existing open 15m signals aren't specially migrated.** Binance still
  serves 15m candles, so `outcome_tracker` keeps closing them out normally.
  Once `15m` drops out of `TRADING_SESSIONS`, those rows just fall back to
  the 14-day default `max_open_days` (pulled from swing's config) instead of
  2 days if they haven't closed already — cosmetic, self-resolving.

## Data model / config (`signals/models.py`)

- `TradingSession` gains a `strategy: str` field.
- `TRADING_SESSIONS` becomes:
  - `scalp`: `timeframe="5m"`, `strategy="sr_bounce"`,
    `confluence_timeframe="1h"`, `max_open_days=2`.
  - `swing`: `timeframe="1h"`, `strategy="ema_cross"`,
    `confluence_timeframe=None`, `max_open_days=14` (unchanged).
- `TIMEFRAME_MINUTES` gains `"5m": 5`.
- `SIGNAL_STRATEGIES` gains `"sr_bounce"` — kept as the canonical list of
  valid strategy ids (used by `NO_SETUP_PROMPTS`/`_format_indicators` in
  `composer.py` and displayed as a badge from each row's stored
  `indicators.strategy`), even though nothing reads it to pick the active
  strategy anymore.
- `BotSettings.signal_strategy` field is removed. `signals/storage.py`'s
  `fetch_bot_settings` drops the `signal_strategy`/`SIGNAL_STRATEGIES`
  read-and-validate block and the corresponding `BotSettings(...,
  signal_strategy=strategy)` argument.

## New strategy: `signals/strategies/sr_bounce/detector.py`

- Constants: `PIVOT_LEFT = PIVOT_RIGHT = 2`, `STRUCTURE_LOOKBACK = 120`
  (candles — 120×5m = 10h), `LEVEL_TOLERANCE_PCT = 0.001` (0.1%),
  `MIN_TOUCHES = 2`, `ATR_STOP_BUFFER = 0.5`, `RISK_REWARD = 2.0`.
- `pivot_lows`/`pivot_highs`: same local-min/max definition style as
  `ict_smc` (new code, not imported from it — the two detectors stay
  independent).
- Level clustering: group pivot prices within `LEVEL_TOLERANCE_PCT` of each
  other; a group qualifies as a tradeable level once it has `>= MIN_TOUCHES`
  members. Support levels come from clustered pivot lows, resistance from
  clustered pivot highs.
- Signal firing, checked on the latest closed candle:
  - **Long**: candle's low touches/pierces a qualified support level
    (within tolerance) and the candle's close is above it.
  - **Short**: candle's high touches/pierces a qualified resistance level
    and the candle's close is below it.
  - The triggering candle itself is not required to be one of the
    qualifying touches — it fires on the first close-back-through *after*
    the level already has 2+ prior touches.
- `entry = candles[-1].close`; `stop = trigger_low - 0.5*ATR14` (long) /
  `trigger_high + 0.5*ATR14` (short); `take_profit = entry ± 2.0*(entry -
  stop)`. Same `stop` vs. `entry` sanity guard as the other two detectors
  (return `None` if the stop ends up on the wrong side).
- `indicators` dict stored on the setup: `{"strategy": "sr_bounce", "level":
  <price>, "touches": <int>, "atr": atr14[-1]}` — mirrors how `ict_smc`
  reports its own structure fields for the admin dashboard / LLM prompt.
- `detect_setup(symbol, candles, atr14, htf_trend=None)` signature — no
  `ema9`/`ema21`/`rsi14`/`macd_hist`/`adx14` params, since none are used.

## Dispatch (`signals/strategies/router.py`)

- `detect_setup` takes the session's `strategy` (from `TradingSession`,
  threaded through `run.py`) instead of `bot_settings.signal_strategy`, and
  adds a third branch calling `sr_bounce.detect_setup`.

## Run loop (`signals/run.py`)

- `scan_symbol`/`scan_one` pass `trading_session.strategy` instead of
  `settings.signal_strategy`.
- Replace `_fetch_htf_trend` (EMA9/21-based) with
  `_fetch_htf_structure_trend(symbol, timeframe, cfg, session)`: fetches the
  same `HTF_TREND_CANDLE_LIMIT = 30` 1h candles the old function used,
  finds the last 2 pivot highs and last 2 pivot lows within that window
  (`PIVOT_LEFT = PIVOT_RIGHT = 2`, same as `sr_bounce`), returns:
  - `"up"` if the latest pivot high AND latest pivot low are both higher
    than their predecessors,
  - `"down"` if both are lower,
  - `None` otherwise (no clear structure — fails open, same as today).
- This replacement only affects scalp (the only session with
  `confluence_timeframe` set); swing is untouched.
- `ema9`/`ema21`/`rsi14`/`macd_hist`/`adx14` are still computed unconditionally
  for every scan (cheap, and swing/`ema_cross` still needs them) — `router.py`
  simply ignores the ones `sr_bounce` doesn't use, same pattern already used
  for `ict_smc` today.

## Confirmation prompts & no-signal reporting (`signals/composer.py`,
`signals/run.py`)

`composer.py` currently branches only two ways (`ict_smc` vs. an assumed
`ema_cross` shape that reads `ema9`/`rsi`/`macd_hist` unconditionally) —
`sr_bounce`'s indicators don't have those keys, so this needs a third branch
in each spot or prompt-building breaks:

- `NO_SETUP_PROMPTS`: add a `"sr_bounce"` entry describing the rule ("no
  qualified support/resistance level with a close-back-through on the last
  bar").
- `_format_indicators`: add a branch for `active == "sr_bounce"` that
  formats `level`/`touches`/`atr` instead of assuming `ema9`/`rsi`/
  `macd_hist` exist.
- `build_messages`'s `strategy_line`: add a third line for `sr_bounce`
  ("Strategy: Support/resistance bounce (price action)").

`run.py`'s `scan_symbol` "no setup found" branch currently special-cases
`ict_smc` to build a stripped-down indicators dict (since it doesn't need
`ema9`/`rsi`/`macd_hist` either) and otherwise assumes the `ema_cross` shape.
Add the same kind of `sr_bounce` branch (indicators = `{"strategy":
"sr_bounce", "atr": atr14[-1]}` when no qualifying level/trigger exists),
rather than falling through to the `elif indicators is None` path meant for
`ema_cross`.

## Admin UI (`web/src/app/admin/ai/settings/page.tsx`,
`web/src/lib/supabase/admin.ts`, `web/src/app/admin/actions.ts`)

- Remove the "Signal strategy" `<select>` and its server action / validation
  against `SIGNAL_STRATEGIES`.
- `BotSettings` type (web-side) drops `signalStrategy`.
- No change needed to how `symbols` / `minAlertConfidence` are configured.

## Testing

- New `tests/test_sr_bounce_detector.py`: level requires 2 touches before
  it's tradeable (1 touch → no signal), entry only fires on the
  close-back-through candle (not on a touch that doesn't close through),
  stop/target math, and the guard that rejects a setup when the computed
  stop lands on the wrong side of entry.
- New/updated coverage in `tests/test_pipeline.py` or a new
  `test_htf_structure_trend` test for `_fetch_htf_structure_trend`'s
  up/down/None classification.
- Update anything in `tests/test_config.py`, `tests/test_pipeline.py` that
  currently asserts on `bot_settings.signal_strategy` or the 15m scalp
  timeframe.
- Update `web/src/app/admin/ai/settings/page.tsx` related tests (if any)
  and remove `signalStrategy` from web-side fixtures/types.

## Out of scope

- Any change to the swing session.
- Backfilling or re-scoring already-open 15m signals under the new scheme.
- Dropping the now-unused `bot_settings.signal_strategy` column from
  Supabase (left in place, harmless).
- Reconciling this design with the (separately in-progress, not yet merged)
  multi-level TP1/TP2/TP3 work — `sr_bounce` is built against today's
  single `take_profit` field, matching `ema_cross`/`ict_smc` as they exist
  now. If/when TP1/TP2/TP3 lands, `sr_bounce` will need the same follow-up
  update the other two detectors get.
