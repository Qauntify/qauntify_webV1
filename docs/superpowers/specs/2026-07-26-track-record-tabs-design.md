# Tabbed navigation on the track-record page

## Goal

Restructure the public `/track-record` page from one long scroll into a tabbed
layout: the headline stat tiles stay pinned on top, and the detail sections are
split across four tabs the visitor clicks between.

## Decisions (approved)

- **Four tabs:** Overview (equity curve) · Breakdown (by strategy + by symbol) ·
  Calendar (daily heatmap + monthly P&L) · Trades (recent closed trades).
- **Pinned:** the `StatTiles` KPI row + the "updated" pill stay above the tab bar
  (always visible); `MethodologyNote` stays in the footer.
- **Client-side tabs:** `useState` visibility toggle over already-fetched data —
  no routing, no new fetch, no data-layer changes.
- **Reuse:** the existing section components (`EquityCurve`, `Breakdown`,
  `Heatmap`, `PnLCalendar`, `RecentTrades`) are rendered unchanged inside the
  tab panels.

## Out of scope (YAGNI)

- URL-synced tabs (`?tab=…`) / deep-linking. (Easy follow-up if wanted.)
- Any change to the derivation layer or the section components themselves.
- Tabs in the empty state (no closed trades → the existing empty card, no tabs).

## Architecture

### `web/src/components/track-record/TrackRecordTabs.tsx` (client component)

`"use client"`. Props: `{ equity, byStrategy, bySymbol, daily, recent }` (the
already-derived pieces from `TrackRecord`, typed via the exports of
`@/lib/track-record`). Holds `const [tab, setTab] = useState<TabId>("overview")`
where `TabId = "overview" | "breakdown" | "calendar" | "trades"`.

Renders a tab bar (a `role="tablist"` of buttons) styled to match the app —
inactive `text-slate`, active `text-accent` with a bottom border/pill — then the
active panel:

- `overview` → `<EquityCurve points={equity} />` in the existing card wrapper.
- `breakdown` → `<Breakdown title="By strategy" rows={byStrategy} />` +
  `<Breakdown title="By symbol" rows={bySymbol} />` (the existing 2-col grid).
- `calendar` → the "Daily net" `<Heatmap daily={daily} />` card + the
  "Monthly P&L" `<PnLCalendar daily={daily} />` card.
- `trades` → the "Recent closed trades" `<RecentTrades trades={recent} />` card.

The section components are pure presentational (no server-only APIs), so
rendering them inside a client component is fine.

### `web/src/app/track-record/page.tsx` (server component)

Keeps: `Nav`, header (`h1` + "updated" pill), and the pinned `StatTiles`. The
stacked detail-section markup (equity/breakdown/heatmap/calendar/trades cards)
is replaced by a single
`<TrackRecordTabs equity={tr.equity} byStrategy={tr.byStrategy} bySymbol={tr.bySymbol} daily={tr.daily} recent={tr.recent} />`.
`MethodologyNote` and `Footer` stay below. The empty-state branch is unchanged.

## Testing

`web/tests/components/track-record/TrackRecordTabs.test.tsx` (vitest +
@testing-library/react, jsdom):

- Renders the four tab labels; the Overview panel is shown by default (the
  equity-curve container / "Cumulative R" copy is present).
- Clicking the "Trades" tab switches the panel (recent-trades content appears;
  the equity-curve heading no longer shown).

Provide minimal sample props (a couple of `EquityPoint`s, one `BreakdownRow`
each, one `DailyNet`, one `ClosedTrade`). Plus `cd web && npm run build`.

## Rough build order

1. `TrackRecordTabs.tsx` component + RTL test.
2. Wire it into `page.tsx` (replace the stacked sections; keep tiles pinned).
