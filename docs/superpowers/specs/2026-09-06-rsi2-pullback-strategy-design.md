# RSI(2) Pullback-in-Trend, Maker-Fill Entry (`rsi2_pullback`)

## Goal

Add a new 5m detector for the `super_scalp`/`xau_scalp` slot, currently
producing zero signals since `ict_fvg` was pulled (`docs/ict-fvg-backtest-
results.md`: net −1.253R/trade, no measurable edge at any confirmation tier).
Admin-selectable, **not** assigned to a live session by this work —
`TRADING_SESSIONS` stays unchanged until the long-history backtest reports a
number, exactly how `orb_rvol` was measured before (not) being promoted and
`cloud_mss` was measured before being promoted.

## Why this concept, not another attempt at the same mistake

Every strategy this repository has measured at 15m-or-faster has lost — seven
for seven, most recently `ict_fvg` (−1.253R/trade) and `msnr` (−0.168R/trade,
1h, included here because even that timeframe wasn't automatically safe).
`cost_r()` charges a fee that's a percentage of **price**, divided by the
strategy's **absolute stop distance** — the tighter the stop relative to
price, the worse a fast timeframe bleeds. The one strategy that has ever
measured profitable, `bbma_reentry` (+0.120R/trade, 1h/4h, t=+2.77), is a
**pullback-continuation pattern with a hard HTF-trend gate**, not a
liquidity-sweep or S/R-bounce pattern. `rsi2_pullback` targets the same
strategic family, deliberately, plus two structural changes aimed directly at
the cost mechanism itself rather than at the timeframe:

1. **Wide, ATR-anchored stop** (target ~1.5×ATR total risk, matching the
   classic Donchian/Turtle-style ATR-stop convention — see "Considered and
   rejected" just below) instead of `ict_fvg`'s 0.15–0.25×ATR buffer. Directly
   attacks the denominator in `cost_r = (bps/10000) * |entry| / risk`.
2. **Resting-limit entry**, earning the 4bps maker rate instead of 20bps
   taker — the same mechanism `sr_limit` already uses and that this repo's
   own `cost_r()` docstring calls out as the single biggest lever available.

Both levers are real and independently verified in this repo already
(`sr_limit`'s own doc: maker cut its 15m loss from −0.359R to −0.052R — better,
not a guarantee). Stacking both on a strategy in the repo's one *proven*
family is the most defensible bet available, not a certainty. It will be
measured and reported exactly like every predecessor, including if the
answer is still negative.

### Considered and rejected before writing this spec

**Donchian/Turtle-style breakout with ATR stop.** A real, published, ATR-stop
momentum strategy (Poluri, SSRN 6272239) — but a real backtest of it found
**−55.3% total return on 30-minute BTC**, explicitly "performs poorly on very
short intraday intervals." Named here rather than silently dropped, the same
way `orb_rvol`'s design named the paper's cross-sectional dependency it
couldn't reproduce.

**Cross-sectional relative-volume selection** (the actual source of
`orb_rvol`'s paper's edge). Structurally unavailable with a 2–4 instrument
universe — already established and unchanged since that spec.

## Research basis

Larry Connors' RSI(2) mean-reversion method: buy a short-term oversold dip
**within an ongoing uptrend** (not a countertrend fade), sell a short-term
overbought spike within a downtrend. Widely documented and still actively
adapted to crypto in current industry backtests. Connors' own refinement —
wait for RSI(2) to cross back above the oversold threshold before entering,
rather than entering the instant it dips — is reported to cut whipsaw entries
by roughly 20%.

Known failure mode, explicitly stated in the source material: pure mean
reversion fails badly against a strong trend. This engine already has the
fix for that built in and proven — an HTF hard gate (`msnr`'s `_long_ok`/
`_short_ok` pattern) — so no new machinery is needed to cover it.

## Detector contract

`signals/strategies/rsi2_pullback/detector.py`

```
detect_setup(symbol, candles, atr14, adx14=None, htf_trend=None) -> CandidateSetup | None
```

Same signature shape as `msnr`/`sr_zone` for router uniformity (`adx14`
accepted, not used for gating — recorded in `indicators` only). Timeframe:
**5m**, confluence: **15m** (matches `ict_fvg`'s own choice for the same
primary timeframe).

### Why entry and stop stay tightly coupled — the ict_fvg lesson, applied

`ict_fvg`'s near-zero-risk bug (`docs/ict-fvg-backtest-results.md`) came from
anchoring the stop to a swept bar up to 30 bars in the past while entry
floated on the unrelated current close — fully decoupled, so on rare
coincidence risk collapsed toward zero. This detector is designed to make
that class of bug structurally harder to write, not just guarded against
after the fact:

- The dip bar being retested must be **within `MAX_BARS_SINCE_DIP` (6) bars**
  of the signal bar — an order of magnitude tighter than `ict_fvg`'s 30-bar
  `SWEEP_LOOKBACK`.
- **`MIN_STOP_ATR = 0.5` from day one** (`ict_fvg` shipped with no floor at
  all and needed a production bug fix to add one). At this strategy's target
  risk of ~1.5×ATR, a real setup should never come close to this floor —
  if one ever does, that is itself a sign something is wrong, not a setup
  worth taking.
- Entry is **derived from the same dip bar the stop is anchored to**
  (below), not from an independent "current close" read.

### Algorithm (long; short is the exact mirror)

1. Guard: `len(candles) >= MIN_CANDLES` (30), `atr14[-1] is not None`,
   `atr_value > 0`.
2. HTF gate: `htf_trend != "down"` (hard — matches `msnr`). `None` (unknown)
   passes, same as every other detector's convention.
3. `rsi2 = rsi(closes, RSI_PERIOD=2)` over the full candle window (existing
   `signals.analysis.indicators.rsi` — no new indicator code; it already
   accepts any period).
4. Scan backward from `len(candles) - 2` for the most recent bar `dip_i`
   within `MAX_BARS_SINCE_DIP` bars where `rsi2[dip_i] < RSI_LOW` (10). None
   found → None. (`dip_i` is always strictly before the signal bar — it is
   never re-examined once found stale on a later call, so a detector that
   fires today cannot be "explained" by a dip from last week.)
5. Signal bar `bar = candles[-1]` must be a **retest, not a fresh break**:
   - `bar.low` must reach down to at/near the dip bar's low:
     `candles[dip_i].low - MAX_PIERCE_ATR * atr <= bar.low <= candles[dip_i].low + RETEST_TOLERANCE_ATR * atr`.
   - `bar.close > bar.open` (bullish close — rejection, not continuation
     lower).
6. **Entry (resting limit, sr_limit's exact convention):**
   `entry = min(candles[dip_i].low, bar.open)` — the dip low, or the bar's
   open if it gapped straight through (a gap fills at the open, not the
   level that no longer existed to rest at).
7. **Stop:** `candles[dip_i].low - ATR_STOP_BUFFER (1.5) * atr_value`.
8. Risk check: `stop < entry`, and
   `MIN_STOP_ATR (0.5) <= abs(entry - stop) / atr_value <= MAX_STOP_ATR (3.0)`.
   Two-sided from the first line of code — not added after a diagnosis.
9. Targets: `take_profits_from_risk(entry, stop, "long")` — the engine
   default 1R/2R/3R ladder (no need for `ict_fvg`'s compressed 0.5/1/2 ladder;
   this strategy's stop is already wide, so standard R multiples leave real
   room for a target).
10. `indicators`: `strategy="rsi2_pullback"`, `entry_style="limit"` (so the
    outcome tracker's existing `fills_intrabar()` — already built for
    `sr_limit`, needs no changes — handles this correctly), `rsi2` (value at
    the signal bar), `dip_low`, `dip_time`, `atr`, plus `adx`/`htf_trend`
    when supplied.

### Parameters (initial)

| Name | Value | Meaning |
|---|---|---|
| `RSI_PERIOD` | 2 | Connors' period |
| `RSI_LOW` / `RSI_HIGH` | 10 / 90 | oversold / overbought threshold |
| `MAX_BARS_SINCE_DIP` | 6 | retest must occur within 30 minutes of the dip |
| `MAX_PIERCE_ATR` | 0.25 | how far below the dip low a retest may still reach |
| `RETEST_TOLERANCE_ATR` | 0.15 | how far above the dip low still counts as "reached" it |
| `ATR_STOP_BUFFER` | 1.5 | stop distance beyond the dip low (Donchian-convention ATR stop) |
| `MIN_STOP_ATR` | 0.5 | floor — the `ict_fvg` fix, built in from the start |
| `MAX_STOP_ATR` | 3.0 | ceiling — matches `msnr`/`ict_smc`'s range |
| `MIN_CANDLES` | 30 | RSI(2) warm-up plus margin |

## Measurement — the actual gate

`scripts/rsi2_pullback_history_report.py`, modeled directly on
`scripts/msnr_history_report.py`: SHA256-verified Binance monthly archives
(`scripts/history_provenance.py`), BTC/ETH only (Binance lists no gold — same
caveat every prior report carries), replayed through `backtest_windowed` on
the 200-bar live-matching window, HTF trend from `htf_trend_series` at 15m.

**`bps=MAKER_BPS` passed to `backtest_windowed`**, mirroring exactly how
`scripts/history_sweep.py` scores `sr_limit` — "the fee tier is per strategy,
not per symbol... charging \[a resting-limit strategy\] taker fees measures a
strategy nobody would run." This is the one place this report's methodology
genuinely differs from `ict_fvg_history_report.py`, for a documented,
mechanical reason, not a discretionary one.

No pipeline-level hard gate exists yet for this strategy (it isn't wired into
`scan.py` until after measurement), so no `gate=` callback is needed — same
situation `msnr_history_report.py` was in.

Reported in `docs/rsi2-pullback-backtest-results.md`, same shape as every
report before it: headline table, distribution sanity check (median vs mean,
worst-trade plausibility — the exact check that caught `ict_fvg`'s bug),
comparison against every other strategy's net/trade, honest verdict
regardless of outcome.

## File layout

```
signals/strategies/rsi2_pullback/
  __init__.py    # re-export detect_setup (mirrors ict_fvg, msnr)
  detector.py    # entry / stop / TP rules — single file, no windows.py
                 # needed (no session/time-anchor logic, unlike orb_rvol)
```

## Integration (mirrors `orb_rvol`'s wiring — admin-selectable, not session-pinned)

| File | Change |
|---|---|
| `signals/strategies/rsi2_pullback/` | new `detector.py`, `__init__.py` |
| `signals/strategies/router.py` | dispatch `rsi2_pullback` |
| `signals/models.py` | add `"rsi2_pullback"` to `SIGNAL_STRATEGIES` and `ADMIN_SELECTABLE_STRATEGIES`; `TRADING_SESSIONS` unchanged |
| `signals/pipeline/scan.py` | add to the `_no_setup_indicators` strategy tuple |
| `signals/pipeline/composer.py` | no-setup reason, indicator formatting, strategy line |
| `signals/rag/playbook.py` | confirm-gate + reject-cues chunks |
| `signals/analysis/backtest.py` | `STRATEGY_TIMEFRAMES["rsi2_pullback"] = "5m"`, `CONFLUENCE_TIMEFRAMES["rsi2_pullback"] = "15m"` |
| `web/src/lib/supabase/admin.ts` | add to the `SIGNAL_STRATEGIES` dropdown array |
| new `supabase/migrations/*.sql` | drop + re-add `bot_settings_signal_strategy_check` to include `rsi2_pullback`, mirroring the `orb_rvol` migration |
| `tests/strategies/test_rsi2_pullback_detector.py` | new |
| `tests/core/test_strategy_choices.py` | no rule changes needed — existing assertions must keep passing once the sources above agree |

## Testing

TDD, synthetic candle series, same style as `sr_limit`'s and `msnr`'s tests.

- RSI(2) dip found, retest bar bullish and touches the dip low within
  tolerance → long, `entry_style == "limit"`, entry at the dip low (or bar
  open on a gap-through), stop below it
- Bearish mirror → short
- Dip older than `MAX_BARS_SINCE_DIP` → None
- Retest bar's low pierces more than `MAX_PIERCE_ATR` below the dip low →
  None (failed retest, not a rejection)
- Retest bar closes bearish (`close <= open`) → None
- HTF trend opposes (`down` for a long candidate) → None
- Risk below `MIN_STOP_ATR` or above `MAX_STOP_ATR` → None
- A gap-through bar prices entry at `bar.open`, not the (no-longer-reachable)
  dip low
- Router dispatch for `"rsi2_pullback"`

## Out of scope

- Assigning `rsi2_pullback` to a live `TRADING_SESSIONS` slot (deferred to
  the backtest result, same as `orb_rvol`).
- Gold (`XAUUSD`) coverage — no SHA256-verified long-history source exists
  for it in this repo's toolkit; explicitly not measured here (per the
  earlier decision to keep full rigor on crypto rather than a weaker
  gold-specific measurement).
- Any variant of Connors' original "buy the instant RSI(2) dips" rule
  without the retest/limit-fill geometry — this design deliberately trades
  Connors' literal entry rule for the maker-fill mechanism, which is the
  point of this strategy relative to every fast-timeframe predecessor.
- A/B testing the RSI threshold or ATR multiples against this same
  historical sample after seeing a result — would be exactly the
  curve-fitting this series has consistently refused to do.
