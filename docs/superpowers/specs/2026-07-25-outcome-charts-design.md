# Outcome charts on TP3 / SL

## Goal

When a signal reaches its **final result** — a full win (`tp3_hit`) or a loss
(`sl_hit`) — render a chart that proves how the trade played out: the setup
context, the real price path, the bars where each target filled, and a bold
HIT / STOP flag. Attach it to the Telegram outcome alert and show it on the
dashboard next to the setup chart.

This closes the loop opened by the setup-chart feature: users saw *how* the AI
set the trade up; now they see *that it played out* (or didn't — losses are
shown honestly). It is the highest trust-per-effort follow-up because it reuses
the entire `signals/chart/` package.

## Decisions (approved)

- **When:** only the trade's terminal result — `tp3_hit` (win) and `sl_hit`
  (loss), plus legacy `tp_hit`. Partial `tp1_hit`/`tp2_hit` stay as the current
  lightweight text alerts. `expired` doesn't send an outcome alert today, so it
  is naturally out of scope.
- **Surfaces (Approach A):** Telegram outcome alert as a **photo**, AND store
  `outcome_chart_url` on the signal so the **web card** shows it too. Mirrors the
  setup-chart architecture.
- **Storage:** URL only — no `outcome_chart_data` JSON (that was Approach C).
- **Loss honesty:** on an `sl_hit` that first banked TP1/TP2, still show those
  ✓ marks — the honest "hit TP1 then reversed" story.
- **Candles:** merge the stored setup snapshot with the price-path candles the
  outcome tracker already fetched — no new market fetch.
- **Visual vocabulary (locked via mockup):** dimmer/banded setup context vs live
  trade, entry/SL/TP lines, per-target ✓ marks, the ✅ TP3 HIT / 🛑 SL HIT flag,
  captured-move shading, and a result badge (`+R` / `+%`).

## Out of scope (YAGNI)

- Charts for partial hits (TP1/TP2) or `expired` closes.
- `outcome_chart_data` JSON / interactive web outcome chart (deferred; only the
  URL is stored).
- Re-generating outcome charts for already-closed historical signals.

## Architecture

### Trigger & candle source — `signals/outcome_tracker.py`

`track_open_signals` already, per open signal: fetches candles covering the
trade's life (`window`), advances the outcome, and calls `send_outcome_alert`
for TP/SL hits. When the run's final `outcome` for a signal is terminal
(`tp3_hit` / `sl_hit` / `tp_hit`):

1. Build the merged candle series: normalize `row["chart_data"]["candles"]` (the
   setup snapshot, stored as `{t,o,h,l,c}` dicts) into `Candle` objects and
   merge with `window`, **deduped by `open_time` and sorted**. If
   `chart_data`/snapshot is missing (older signals), fall back to `window` only.
2. `entry_time` = the boundary between snapshot and path (the last snapshot
   candle's `open_time`); when there is no snapshot, the first path candle.
3. Render + upload the outcome chart (non-fatal — see below), persist
   `outcome_chart_url`, and pass it to `send_outcome_alert`.

### Outcome plan builder — `signals/chart/outcome_plan.py`

`build_outcome_plan(signal_row, outcome, candles) -> list[Annotation]` returns
primitives (reusing `zone`/`level`/`marker` from `annotations.py`):

- Entry/SL/TP1-3 as `level`s (reusing the setup roles) + an `Entry` marker.
- A **direction-aware first-cross** scan over the merged candles marks
  **TP1 ✓ / TP2 ✓** where each filled — long: first bar `high ≥ TP`; short:
  first bar `low ≤ TP`.
- The resolving flag: `✅ TP3 HIT` at the first bar crossing TP3 (win), or
  `🛑 SL HIT` at the first bar crossing SL (long: `low ≤ SL`; short:
  `high ≥ SL`) for a loss.
- A **captured-move `zone`** (role `win`, green) entry→TP3 on a win, or
  (role `loss`, red) entry→SL on a loss.
- On an `sl_hit`, the earlier TP1/TP2 ✓ marks are still added when the price path
  crossed them before the SL bar.

Pure function → unit-testable with synthetic candles.

Direction-aware crossing lives in a small helper
`first_cross(candles, level, direction, kind)` (`kind` ∈ `tp`/`sl`) so it is
tested independently for long and short.

### Renderer — `signals/chart/render.py` (shared refactor)

Extract the mpf boilerplate (build DataFrame, style, `mpf.plot`) into
`_base_plot(candles) -> (fig, ax, x_of, last_x)`, used by both the existing
`render_chart` and the new
`render_outcome_chart(candles, plan, signal, entry_time, outcome) -> bytes`.

`render_outcome_chart` additionally:
- draws a subtle **shaded band over the pre-entry region + a divider line at
  `entry_time`** (mplfinance can't dim individual candles, so this gives the
  "setup vs live-trade" read),
- draws the plan via the existing `_draw`,
- draws the big HIT / STOP flag,
- applies the existing `_price_bounds` y-limit fix so every level is visible,
- sets a result-badge title (`SYMBOL · TF · DIR · ✅ TP3 HIT · +1.5R (+x.xx%)`).

New renderer color roles: `win` (green fill `#34d399`) and `loss`
(red fill `#fb7185`) in `ROLE_FILL`. Very long swing trades have their oldest
pre-entry context trimmed to keep the window readable (cap ≈120 bars).

### Upload — `signals/chart/upload.py`

Add an optional `suffix: str = ""` param so the object key is
`{signal_id}{suffix}.png`; outcome charts pass `suffix="-outcome"` →
`{signal_id}-outcome.png`. Existing setup-chart callers are unchanged.

### Non-fatal wrapper — `signals/chart/outcome_pipeline.py`

`attach_outcome_chart(signal_row, outcome, candles, *, supabase_url,
service_key, session=None) -> str | None` builds the plan, renders, uploads, and
returns the URL — swallowing any exception (mirroring `attach_chart`). A chart
failure must never drop or delay the outcome alert.

### Storage & DB (`supabase/schema.sql`, `signals/storage.py`)

- `alter table public.signals add column if not exists outcome_chart_url text;`
- The terminal-close update in the tracker writes `outcome_chart_url` (extend
  `update_signal_outcome` with an optional field, or a focused setter — chosen
  during planning to match the existing call shape).

### Telegram (`signals/telegram_client.py`)

`send_outcome_alert(signal_row, outcome, ...)` gains the same branch as
`send_alert`: if `signal_row["outcome_chart_url"]` is set, send a **photo** with
`format_outcome_alert(...)` (already short) as the caption; otherwise the current
text message.

### Web (`web/src/lib/signals.ts`, dashboard card)

Add `outcomeChartUrl: string | null` to the `Signal` type + `outcome_chart_url`
to `SignalRow` + map it in `parseRow` (queries are `select=*`). On a **closed**
signal's card, show the outcome image labelled "Outcome" beneath the setup
chart. Uses a plain `<img loading="lazy">` (see `web/AGENTS.md` re: the pinned
Next.js).

## Testing

- `first_cross` — long and short, tp and sl kinds.
- `build_outcome_plan` — win (TP✓ ×2 + TP3 flag + win zone), loss (SL flag +
  loss zone), and loss-after-partial (TP1 ✓ still shown).
- candle merge — snapshot + path dedupe by `open_time` and sort; snapshot-missing
  fallback.
- `render_outcome_chart` — returns valid PNG bytes for a representative plan;
  degenerate plan still renders.
- `send_outcome_alert` — photo when URL present, text fallback when not.
- Non-fatal — a render/upload exception yields a text-only outcome alert and the
  outcome is still persisted.
- Web — `parseRow` maps `outcome_chart_url`; `npm run build` clean.

## Rough build order

1. DB column.
2. `first_cross` helper + `build_outcome_plan` (pure, TDD).
3. `_base_plot` refactor + `render_outcome_chart`.
4. `upload_chart` `suffix` param.
5. `attach_outcome_chart` non-fatal wrapper.
6. Wire into `track_open_signals` + persist `outcome_chart_url`.
7. `send_outcome_alert` photo-or-text.
8. Web display.
