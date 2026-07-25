# Live Track-Record page

## Goal

A public `/track-record` page that turns real closed trades into a credible,
auto-updating performance story — equity curve, win rate, expectancy,
per-strategy/symbol breakdowns, a daily heatmap, and a recent-closed-trades log
with the outcome charts. Everything is computed browser-side from closed-signal
rows. This is the conversion companion to the setup/outcome charts: prospects
see the aggregate proof, honestly (wins *and* losses), while live/open signals
stay the gated product.

## Decisions (approved)

- **Visibility:** public — logged-out visitors see the full aggregates AND the
  closed-trade log; open/live signals remain gated.
- **Compute location (Approach A):** browser-side from closed-signal rows. Pure,
  unit-tested derivation functions. A server-side aggregate RPC is a documented
  future optimization, not built now.
- **R model:** win = `|exitTP − entry| / |entry − stop|` (exit = TP3, or
  `take_profit` for legacy `tp_hit`); loss (`sl_hit`) = `−1R`. Conservative:
  a trade that banked TP1/TP2 then reversed to SL still counts as −1R.
- **Sections + order (locked via mockup):** stat tiles → equity curve →
  strategy/symbol breakdown → daily heatmap → recent closed trades →
  methodology note.

## Out of scope (v1, YAGNI)

- Server-side aggregate RPC (browser-side compute is enough at current volume).
- Timeframe filter, "vs backtest" comparison, best/worst callouts, subscribe CTA
  on the page (all easy follow-ups).
- Scale-out R accounting for partial exits (kept conservative: SL = −1R).
- Changes to existing stats functions (`getStats`, `getDailyPnLStats`, etc.).

## Architecture

### Data access — `supabase/schema.sql` (one policy)

Add an anon SELECT policy on `public.signals` for terminal statuses:

```sql
drop policy if exists "anon closed-trade access" on public.signals;
create policy "anon closed-trade access"
    on public.signals for select
    to anon
    using (status in ('tp_hit', 'tp3_hit', 'sl_hit'));
```

RLS policies are permissive (OR-combined), so this stacks with the existing
`"anon preview access"` (24h) policy: anon can read historical **closed** trades
(non-actionable) plus the 24h preview, but still cannot read older **open**
signals. The `authenticated` "member full access" policy is unaffected.

### Derivation layer — `web/src/lib/track-record.ts`

`getTrackRecord(accessToken?)` fetches closed signals with a **lean select**
(not `select=*`):

```
select=id,symbol,timeframe,direction,entry,stop_loss,take_profit,
take_profit_1,take_profit_2,take_profit_3,status,created_at,closed_at,
indicators,outcome_chart_url
&status=in.(tp_hit,tp3_hit,sl_hit)&order=closed_at.asc.nullslast
```

It maps rows to a `ClosedTrade` shape and derives everything through pure
functions (no network — directly unit-testable):

- `tradeR(trade) -> number` — win/loss R per the R model above; guards
  `risk === 0` (returns 0).
- `summarize(trades) -> Summary` — `{ total, wins, losses, winRate, netR,
  avgR, bestStreak, updatedAt }`. `bestStreak` = longest run of consecutive
  wins by `closed_at`. `updatedAt` = max `closed_at`.
- `equityCurve(trades) -> { t: string; r: number }[]` — cumulative R ordered by
  `closed_at` ascending, starting at 0.
- `breakdown(trades, keyOf) -> { name, winRate, netR, count }[]` — used with
  `t => t.strategy`, `t => t.symbol`, `t => t.timeframe`; sorted by net R desc.
- `dailyNet(trades) -> { date: string; net: number }[]` — net R per calendar day
  (by `closed_at`), for the heatmap.
- `recentTrades(trades, n) -> ClosedTrade[]` — latest N by `closed_at` desc,
  carrying `outcomeChartUrl`.

`strategy` is read from `indicators.strategy` (falls back to `"ema_cross"` when
`ema9` is present, `"—"` otherwise — mirrors the engine's own detection). Any
ordering/bucketing by `closed_at` falls back to `created_at` when `closed_at` is
null (matches the existing `getDailyPnLStats` behavior).

`getTrackRecord` returns a `TrackRecord` object bundling `summary`,
`equity`, `byStrategy`, `bySymbol`, `byTimeframe`, `daily`, and `recent`.

### Page + components — `web/src/app/track-record/page.tsx`, `web/src/components/track-record/`

Public server component: calls `getTrackRecord()` with the anon key and renders,
in order:

- `StatTiles` — win rate, net R, avg/trade, best streak.
- `EquityCurve` — inline SVG line + area of cumulative R; zero baseline.
- `Breakdown` — horizontal bars (win rate width, net R label) for strategy and
  symbol side by side.
- `Heatmap` — grid of daily-net squares (green/red intensity), last ~13 weeks.
- `RecentTrades` — table: symbol·TF, direction, ✓ TP3 / ✗ SL result, R, age,
  and the `outcomeChartUrl` thumbnail linking to the full image.
- `MethodologyNote` — the R definition + "not financial advice".

A nav/CTA link to `/track-record` is added to the landing header. Charts are
built after consulting the `dataviz` skill (palette/marks/legend consistency)
and `web/AGENTS.md` (the pinned Next.js). All chart SVGs are inline and
theme-aware; images use a plain `<img loading="lazy">`.

### Edge / empty states

- Zero closed trades → a friendly empty state ("Your track record fills in as
  trades close") instead of broken charts.
- `risk === 0` → `tradeR` returns 0 (no divide-by-zero).
- All wins / all losses / single trade → equity curve and breakdowns still
  render (min==max handled in the SVG scaling).

## Testing

`web/src/lib/track-record.test.ts` (vitest) covering the pure functions:

- `tradeR` — long win (TP3 R), short win, legacy `tp_hit`, `sl_hit` = −1,
  `risk === 0` guard.
- `summarize` — win rate, net R, avg R, `bestStreak` (consecutive wins),
  `updatedAt`.
- `equityCurve` — cumulative ordering by `closed_at`, starts at 0.
- `breakdown` — grouping + per-group win rate/net R/count, sort order.
- `dailyNet` — day bucketing by `closed_at`.
- empty input → sane zeros/empties for every function.

Plus `cd web && npm run lint && npm run build`.

## Rough build order

1. Anon RLS policy (schema.sql) + apply.
2. `track-record.ts` pure derivation functions + vitest tests.
3. `getTrackRecord` fetch wrapper.
4. Presentational components (`track-record/`), dataviz-guided.
5. `/track-record` page assembling them + empty state.
6. Landing nav/CTA link.
