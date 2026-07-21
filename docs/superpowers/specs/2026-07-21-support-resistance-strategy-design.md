# Support/Resistance bounce strategy (`sr_zone`)

## Goal

Add a Support/Resistance bounce playbook to the pluggable strategy system.
Buy at support / sell at resistance, but only on a confirmation candle — a
rejection wick that closes back inside the range. Admin-selectable for the
swing (1h) session alongside `ema_cross` and `ict_smc`.

## Research basis

- S/R levels are horizontal zones formed by clustered swing highs (resistance)
  and swing lows (support). More touches = stronger, but the 1st–2nd touch is
  the highest-quality trade.
- Touching a zone is **not** an entry. Enter only on a confirmation candle
  (rejection wick + close back inside). Skipping confirmation is the classic
  failure mode.
- Stops sit **beyond** the zone with a buffer — zones get wick-hunted, so a
  stop parked on the line dies on noise.
- Bounce trades are mean-reversion: they favour ranging markets, unlike the
  trend strategies. Strong trends blow through levels.

Sources: TradingWithRayner, Capital.com, TradingStrategyGuides, BabyPips,
Entreprenerdly (Python detection).

## Detector contract

`signals/strategies/sr_zone/detector.py`

```
detect_setup(symbol, candles, atr14, adx14=None, htf_trend=None) -> CandidateSetup | None
```

Reuses `pivot_highs` / `pivot_lows` from `ict_smc.detector`.

### Algorithm

1. Guard: `len(candles) >= MIN_CANDLES` and `atr14[-1] is not None`.
2. `window = candles[-STRUCTURE_LOOKBACK:]`. Compute pivot highs and lows
   (`left = right = 2`).
3. Cluster pivot **lows** into support zones, pivot **highs** into resistance
   zones. Pivots within `ZONE_ATR_FRACTION * ATR` of each other merge into one
   zone `{low, high, touches}`. Keep zones with `touches >= MIN_TOUCHES`.
4. Confirmation entry on the latest closed bar:
   - **Long (support bounce):** bar low pierces a support zone
     (`bar.low <= zone.high`) but closes back above it (`bar.close > zone.high`),
     bullish body (`close > open`), lower rejection wick
     `>= MIN_REJECTION_WICK_ATR * ATR`. `entry = bar.close`,
     `stop = zone.low - ATR_STOP_BUFFER * ATR`.
   - **Short (resistance rejection):** mirror at a resistance zone. `entry =
     bar.close`, `stop = zone.high + ATR_STOP_BUFFER * ATR`.
   - Pick the nearest qualifying zone to the current close.
5. Gates:
   - **ADX ceiling** (not floor): if `adx14[-1]` given and `>= ADX_RANGE_MAX`,
     skip — strong trend, levels unreliable. (Opposite of `ema_cross`/`ict_smc`,
     which require a trend.)
   - `htf_trend` filter, same convention as `ema_cross`: skip long when
     `htf_trend == "down"`, skip short when `htf_trend == "up"`.
6. Risk: reject stops wider than `MAX_STOP_ATR * ATR`. Targets `1R/2R/3R` via
   `take_profits_from_risk`.
7. `indicators` dict: `strategy="sr_zone"`, `side` ("support"/"resistance"),
   `zone_low`, `zone_high`, `touches`, `atr`, plus `adx` / `htf_trend` when set.

### Parameters (initial)

| Name | Value | Meaning |
|---|---|---|
| `PIVOT_LEFT` / `PIVOT_RIGHT` | 2 / 2 | swing pivot window (reused) |
| `STRUCTURE_LOOKBACK` | 120 | bars scanned for zones |
| `MIN_CANDLES` | 30 | minimum history |
| `ZONE_ATR_FRACTION` | 0.5 | pivot clustering width |
| `MIN_TOUCHES` | 2 | tested-level threshold |
| `MIN_REJECTION_WICK_ATR` | 0.15 | confirmation wick size |
| `ATR_STOP_BUFFER` | 0.5 | stop distance beyond zone |
| `MAX_STOP_ATR` | 2.5 | reject wide stops |
| `ADX_RANGE_MAX` | 35.0 | skip strong trends |

## Integration (mirrors `ict_smc` wiring)

| File | Change |
|---|---|
| `signals/strategies/sr_zone/` | new `detector.py` + `__init__.py` |
| `strategies/router.py` | dispatch `sr_zone` |
| `models.py` | add `"sr_zone"` to `SIGNAL_STRATEGIES` |
| `run.py` | no-setup logging branch |
| `composer.py` | no-setup reason, indicator formatting, strategy line |
| `rag/playbook.py` | confirm-gate + reject-cues chunks |
| `web/src/lib/supabase/admin.ts` | add to `SIGNAL_STRATEGIES` dropdown |
| `tests/test_sr_detector.py` | bounce long, rejection short, negatives, router |

## Testing

Unit tests build synthetic candle series (as the other detector tests do):
a clustered support zone + a confirmation bounce bar → long; mirror for a
resistance rejection → short; a bar that touches without closing back inside →
None; a single-touch level (below `MIN_TOUCHES`) → None; router dispatch.

## Out of scope

Breakout + retest entries (deferred). TP anchored to the next opposing zone
(uses R-multiples for engine consistency instead).
