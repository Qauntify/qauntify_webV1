# Annotated setup charts on every signal

## Goal

When the engine drops a signal, also produce a **real chart image** showing the
recent candles with the exact things the strategy reasoned about drawn on top —
FVG box, CHoCH level + ✓, liquidity sweep, S/R zone, EMAs, and the entry / SL /
TP lines. The image is delivered on **Telegram** (as a photo) and shown on the
**web dashboard**. The structured data behind the image is also stored so the
web view can become interactive later without re-architecting.

This exists because users don't trust or understand signals they can't *see* —
"how did the AI set this up?" The picture answers that at a glance.

## Decisions (approved)

- **Render location:** server-side in Python at signal time (Approach C). The
  engine already has the candle window + indicators in hand, and it runs on
  **GitHub Actions runners** (`python -m signals.run` / `signals.xau_scan`), not
  Vercel serverless — so there are **no bundle-size limits** and a real charting
  library is safe.
- **Approach C ("PNG now, wired for interactive later"):** generate a static PNG
  that works on every surface *now*, and *also* persist the structured chart plan
  + a candle snapshot so a future interactive web chart is a drop-in from the same
  data. No dead-ends.
- **Surfaces:** Telegram + web, both equally. One image serves both.
- **Scope:** all five strategies, each marking its own elements (see table).
- **Library:** `mplfinance` (matplotlib) for native candlesticks + overlays.
- **Visual vocabulary (locked via mockup):** FVG box, CHoCH level + ✓, swept
  liquidity + sweep marker, entry / SL / TP1–3. Dark background, teal up /
  rose down, matching the existing app palette.

## What each strategy marks

| Strategy   | Elements drawn |
|------------|----------------|
| `ict_fvg`  | FVG box, CHoCH level + ✓, swept liquidity + sweep marker, entry/SL/TP |
| `ict_smc`  | CHoCH level + ✓, swept liquidity + sweep marker, entry/SL/TP (no FVG) |
| `sr_zone`  | Support/Resistance zone box (+ touch count), entry/SL/TP |
| `ema_cross`| EMA9 & EMA21 lines, the cross marker, entry/SL/TP |
| `ce_lwma`  | Chandelier trail line, LWMA200 line, premium/discount tint, entry/SL/TP |

## Out of scope (v1, YAGNI)

- **Interactive web chart** — the data is stored for it, but building the
  lightweight-charts interactive view is a later phase. v1 shows the static image.
- **"No-signal" report images** — signals only.
- **Back-filling images for historical signals** — new signals only, going forward.

## Architecture

### The annotation schema (core abstraction)

One normalized "chart plan" — a list of simple drawable primitives that **every**
strategy emits, so the renderer never needs to know which strategy it is drawing.

- **`zone`** — shaded box: `{price_top, price_bottom, start_time, label, role}`
  (FVG, S/R zone, premium/discount).
- **`level`** — horizontal line: `{price, start_time?, label, style, role}`
  (CHoCH level, swept low/high, chandelier trail).
- **`marker`** — labeled dot on a candle: `{time, price, label, order?, role}`
  (① sweep, ② CHoCH ✓, ③ retest→entry).
- **`series`** — line over the candles: `{points:[{time,value}], label, role}`
  (EMA9, EMA21, LWMA200 — **recomputed from candles at render time**, not stored).
- Entry / SL / TP are `level`s with roles `entry` / `stop` / `target`.

`role` (e.g. `bullish-structure`, `liquidity`, `entry`, `stop`, `target`) maps to
the brand palette **inside the renderer** — detectors stay dumb about colors.

### New module: `signals/chart/`

- **`plan.py`** — `build_chart_plan(candles, signal) -> list[Annotation]`.
  Dispatches on `indicators["strategy"]`; one small pure builder per strategy.
  Pure functions → unit-testable (e.g. "assert an FVG zone exists at 2005.7–2007.0").
- **`render.py`** — `render_chart(candles, plan, signal) -> bytes`. mplfinance
  draws ~50–60 candles + the plan, styled to brand, returns **PNG bytes
  (1600×900)**. Zones/levels extend to the right edge.
- **`upload.py`** — `upload_chart(png, signal_id) -> url`. Uploads to a new
  Supabase Storage bucket `signal-charts` (public read) via the storage REST API
  with the service key; returns the public URL.

### Detector change (small)

Detectors already compute the bar indices of the sweep / CHoCH / FVG / retest —
they currently discard them. Keep them as **timestamps** in `indicators`
(e.g. `sweep_time`, `choch_time`, `fvg_start_time`, `retest_time`) so markers and
zone starts land on the correct candle. EMA/LWMA lines need no storage — the
renderer recomputes them from the candle window via `signals/indicators.py`.

### Pipeline integration (`run.py` + `xau_scan.py`)

After a signal is confirmed, before it is sent:

1. `plan = build_chart_plan(candles, signal)`
2. `png = render_chart(candles, plan, signal)`
3. `chart_url = upload_chart(png, signal.id)`
4. save signal with `chart_url` + `chart_data`
5. Telegram: send **photo** with the alert as caption

**Failure is non-fatal.** The entire render/upload block is wrapped in
try/except (matching the codebase's "soft-fail open" style). On any error, log a
short line and fall back to the current text-only alert; the signal still saves
and sends. A chart bug can never cost a signal.

### Storage & DB (`supabase/schema.sql`, `storage.py`)

- New Storage bucket `signal-charts` (public read).
- `signals` table:
  - `alter table public.signals add column if not exists chart_url text;`
  - `alter table public.signals add column if not exists chart_data jsonb;`
    (the chart plan + the same ~50–60-bar candle window used to render — the
    "interactive later" data, so the web can redraw without re-fetching).
- `save_signal` writes the two new fields; the `select` lists in `storage.py`
  that feed history include `chart_url`.

### Telegram (`telegram_client.py`)

`send_alert` switches from `sendMessage` to `sendPhoto`. Caption cap is 1024
chars, so the caption carries the essentials (symbol · TF · direction ·
entry/SL/TP · confidence) — the image now conveys the "why," so the long
indicator block is dropped from the caption. If a render/upload failed
(`chart_url` is None), fall back to the existing text `sendMessage`.

### Web dashboard (`web/`)

`SignalsGrid` shows the `chart_url` image — a thumbnail in the card, full-size in
the expanded detail view — lazy-loaded. Signals with `chart_url` null (older
signals or a failed render) fall back to today's text-only card. `chart_url` is
added to the query/lib layer that feeds the grid.

## Testing

- **`plan.py`** — pure-function unit tests per strategy: feed synthetic candles +
  a known signal, assert the returned annotation list contains the expected
  primitives at the expected prices/times (FVG zone bounds, CHoCH level, sweep
  marker, entry/SL/TP levels).
- **`render.py`** — assert it returns non-empty PNG bytes of the expected
  dimensions for a representative plan; smoke-test that an empty/degenerate plan
  still renders candles without raising.
- **Pipeline** — test that a render/upload exception is swallowed and the signal
  still saves + a text fallback alert is produced (the non-fatal guarantee).

## Rough build order

1. Schema + Storage bucket.
2. `render.py` + `plan.py` with the **`ict_fvg`** builder first (data ready; it is
   the reference implementation).
3. Wire into the pipeline + Telegram `sendPhoto`.
4. Web display.
5. The other four strategy builders (`ict_smc`, `sr_zone`, `ema_cross`,
   `ce_lwma`) — each is one small builder function following the same pattern,
   plus any missing event timestamps in that detector.
