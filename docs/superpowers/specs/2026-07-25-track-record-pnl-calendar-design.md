# Monthly P&L calendar on the track-record page

## Goal

Add a monthly calendar section to the public `/track-record` page showing
**net R per day** (green up-days / red down-days, e.g. `+2.5R` / `−1.0R`), with
month/year navigation — a familiar trading-journal view of daily performance.

## Decisions (approved)

- **Metric per day:** net R (consistent with the page's equity curve, Net R,
  and breakdowns — one unit across the whole track record). Not win/loss counts.
- **Data source:** the `tr.daily` (`DailyNet[]` = `{date, net}`) the page already
  derives via `getTrackRecord`. No new fetch, no RLS change (the anon
  closed-trade policy is already live), no admin-calendar edits.
- **Reuse:** the existing admin `DailyPnLCalendar` (count-based) stays untouched;
  we build a focused R-based calendar for the track record that shares its visual
  language (month grid, nav, green/red days).

## Out of scope (YAGNI)

- Touching or generalizing the admin `DailyPnLCalendar`.
- $ P&L (the app has no position sizes — R is the P&L unit).
- Day-level drill-down / clicking a day to see its trades.

## Architecture

### `web/src/lib/month-grid.ts` (pure, tested)

`buildMonthGrid(year, month) -> MonthCell[]` where
`MonthCell = { dateStr: string; dayNum: number; inMonth: boolean }`. Builds a
Monday-start grid for the given month with leading days from the previous month
and trailing days from the next month so the grid fills complete weeks. `dateStr`
is `YYYY-MM-DD` formatted directly from the year/month/day integers (no `Date`
timezone conversion), so it compares cleanly against `dailyNet`'s date keys. Pure — unit-tested
for: correct day count, Monday-start leading padding, trailing padding to a
multiple of 7, and `inMonth` flags.

### `web/src/components/track-record/PnLCalendar.tsx` (client component)

`PnLCalendar({ daily }: { daily: DailyNet[] })`. `"use client"` with `useState`
for the visible month/year (defaults to the latest month present in `daily`, or
current month if empty). Renders month/year nav (prev/next month, jump-to-latest)
and a 7-column grid from `buildMonthGrid`. Each in-month day looks up its net R in
a `Map<dateStr, net>` built from `daily`; days with trades are tinted
green (net > 0) / red (net < 0) / neutral (net === 0) and show the signed R
(e.g. `+2.5R`); days with no trades are blank. Off-month padding days are dimmed.
Tailwind tokens match the page (`border-line`, `bg-card`, `text-ink`,
`text-slate`) and win/loss colors use `emerald-400` / `rose-400`.

### `web/src/app/track-record/page.tsx`

Add a "Monthly P&L" card section (same card styling as the other sections)
rendering `<PnLCalendar daily={tr.daily} />`, placed immediately after the daily
heatmap card. Only shown when not in the empty state.

## Testing

- `web/tests/lib/month-grid.test.ts` (vitest): day count, Monday-start leading
  padding for a month that starts mid-week, trailing padding to a full week,
  `inMonth` flags, and `dateStr` format.
- `cd web && npx tsc --noEmit && npm run build` — component + page compile; the
  page still builds and lists `/track-record`.

## Rough build order

1. `month-grid.ts` helper + vitest test.
2. `PnLCalendar.tsx` component.
3. Wire the section into the track-record page.
