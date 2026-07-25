# Track-Record Tabs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the `/track-record` detail sections into a 4-tab layout (Overview, Breakdown, Calendar, Trades) with the stat tiles pinned on top.

**Architecture:** A new client component `TrackRecordTabs` holds the active-tab `useState` and renders the existing section components in panels; the server page keeps the pinned `StatTiles` + `MethodologyNote` and drops the stacked detail markup for a single `<TrackRecordTabs/>`. No data-layer changes.

**Tech Stack:** Next.js (pinned — see `web/AGENTS.md`), TypeScript, vitest + @testing-library/react, Tailwind.

---

## File Structure

**Create:**
- `web/src/components/track-record/TrackRecordTabs.tsx` — client tab wrapper.
- `web/tests/components/track-record/TrackRecordTabs.test.tsx` — RTL test.

**Modify:**
- `web/src/app/track-record/page.tsx` — pin tiles, replace stacked sections with the tabs.

---

## Task 1: TrackRecordTabs component + test

**Files:**
- Create: `web/src/components/track-record/TrackRecordTabs.tsx`
- Test: `web/tests/components/track-record/TrackRecordTabs.test.tsx`

**Before writing:** read `web/AGENTS.md` (pinned Next.js). This is a client component. It imports the existing presentational section components; win/active color token is `accent` (`text-accent` / `border-accent`, as used in `Nav.tsx` / `WarRoomStage.tsx`); layout tokens `border-line`, `bg-card`, `text-ink`, `text-slate`.

- [ ] **Step 1: Write the failing test**

Create `web/tests/components/track-record/TrackRecordTabs.test.tsx`:

```tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TrackRecordTabs } from "@/components/track-record/TrackRecordTabs";
import type { BreakdownRow, ClosedTrade, DailyNet, EquityPoint } from "@/lib/track-record";

const equity: EquityPoint[] = [
  { t: "2026-07-01T00:00:00Z", r: 1.5 },
  { t: "2026-07-02T00:00:00Z", r: 0.5 },
];
const byStrategy: BreakdownRow[] = [{ name: "ict_fvg", winRate: 60, netR: 3, count: 5 }];
const bySymbol: BreakdownRow[] = [{ name: "XAUUSD", winRate: 66, netR: 5, count: 8 }];
const daily: DailyNet[] = [{ date: "2026-07-01", net: 1.5 }];
const recent: ClosedTrade[] = [
  {
    id: "s1", symbol: "XAUUSD", timeframe: "5m", direction: "long",
    strategy: "ict_fvg", entry: 100, stopLoss: 98, target: 103,
    status: "tp3_hit", closedAt: "2026-07-02T00:00:00Z", outcomeChartUrl: null,
  },
];

function setup() {
  return render(
    <TrackRecordTabs
      equity={equity}
      byStrategy={byStrategy}
      bySymbol={bySymbol}
      daily={daily}
      recent={recent}
    />,
  );
}

describe("TrackRecordTabs", () => {
  it("shows all four tabs and the Overview panel by default", () => {
    setup();
    expect(screen.getByText("Overview")).toBeDefined();
    expect(screen.getByText("Breakdown")).toBeDefined();
    expect(screen.getByText("Calendar")).toBeDefined();
    expect(screen.getByText("Trades")).toBeDefined();
    expect(screen.getByText(/Cumulative R/i)).toBeDefined();
    expect(screen.queryByText(/Recent closed trades/i)).toBeNull();
  });

  it("switches to the Trades panel when the Trades tab is clicked", () => {
    setup();
    fireEvent.click(screen.getByText("Trades"));
    expect(screen.getByText(/Recent closed trades/i)).toBeDefined();
    expect(screen.queryByText(/Cumulative R/i)).toBeNull();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npm test`
Expected: FAIL — cannot resolve `@/components/track-record/TrackRecordTabs`.

- [ ] **Step 3: Write the implementation**

Create `web/src/components/track-record/TrackRecordTabs.tsx`:

```tsx
"use client";

import { useState } from "react";

import { Breakdown } from "@/components/track-record/Breakdown";
import { EquityCurve } from "@/components/track-record/EquityCurve";
import { Heatmap } from "@/components/track-record/Heatmap";
import { PnLCalendar } from "@/components/track-record/PnLCalendar";
import { RecentTrades } from "@/components/track-record/RecentTrades";
import type { BreakdownRow, ClosedTrade, DailyNet, EquityPoint } from "@/lib/track-record";

type TabId = "overview" | "breakdown" | "calendar" | "trades";

const TABS: { id: TabId; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "breakdown", label: "Breakdown" },
  { id: "calendar", label: "Calendar" },
  { id: "trades", label: "Trades" },
];

type Props = {
  equity: EquityPoint[];
  byStrategy: BreakdownRow[];
  bySymbol: BreakdownRow[];
  daily: DailyNet[];
  recent: ClosedTrade[];
};

export function TrackRecordTabs({ equity, byStrategy, bySymbol, daily, recent }: Props) {
  const [tab, setTab] = useState<TabId>("overview");
  return (
    <div>
      <div role="tablist" aria-label="Track record sections" className="mb-4 flex gap-1 overflow-x-auto border-b border-line">
        {TABS.map((t) => (
          <button
            key={t.id}
            role="tab"
            aria-selected={tab === t.id}
            onClick={() => setTab(t.id)}
            className={`-mb-px whitespace-nowrap border-b-2 px-4 py-2 text-sm font-semibold transition-colors ${
              tab === t.id
                ? "border-accent text-accent"
                : "border-transparent text-slate hover:text-ink"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "overview" ? (
        <div className="rounded-xl border border-line bg-card p-4">
          <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate/70">Cumulative R (all closed trades)</div>
          <EquityCurve points={equity} />
        </div>
      ) : null}

      {tab === "breakdown" ? (
        <div className="grid gap-4 md:grid-cols-2">
          <Breakdown title="By strategy" rows={byStrategy} />
          <Breakdown title="By symbol" rows={bySymbol} />
        </div>
      ) : null}

      {tab === "calendar" ? (
        <div className="space-y-4">
          <div className="rounded-xl border border-line bg-card p-4">
            <div className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-slate/70">Daily net (last ~13 weeks)</div>
            <Heatmap daily={daily} />
          </div>
          <div className="rounded-xl border border-line bg-card p-4">
            <div className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-slate/70">Monthly P&amp;L (net R per day)</div>
            <PnLCalendar daily={daily} />
          </div>
        </div>
      ) : null}

      {tab === "trades" ? (
        <div className="rounded-xl border border-line bg-card p-4">
          <div className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-slate/70">Recent closed trades</div>
          <RecentTrades trades={recent} />
        </div>
      ) : null}
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npm test`
Expected: PASS (the 2 new TrackRecordTabs cases + all existing web tests).

- [ ] **Step 5: Commit**

```bash
git add web/src/components/track-record/TrackRecordTabs.tsx web/tests/components/track-record/TrackRecordTabs.test.tsx
git commit -m "feat(track-record): tabbed sections component"
```

---

## Task 2: Restructure the page

**Files:**
- Modify: `web/src/app/track-record/page.tsx`

- [ ] **Step 1: Update the imports**

In `web/src/app/track-record/page.tsx`, replace the current import block:

```tsx
import { Footer } from "@/components/shared/Footer";
import { Nav } from "@/components/shared/Nav";
import { Breakdown } from "@/components/track-record/Breakdown";
import { EquityCurve } from "@/components/track-record/EquityCurve";
import { Heatmap } from "@/components/track-record/Heatmap";
import { MethodologyNote } from "@/components/track-record/MethodologyNote";
import { PnLCalendar } from "@/components/track-record/PnLCalendar";
import { RecentTrades } from "@/components/track-record/RecentTrades";
import { StatTiles } from "@/components/track-record/StatTiles";
import { getTrackRecord } from "@/lib/track-record";
import { relativeTime } from "@/lib/relative-time";
```

with (removes the five section imports now used inside the tabs; adds `TrackRecordTabs`):

```tsx
import { Footer } from "@/components/shared/Footer";
import { Nav } from "@/components/shared/Nav";
import { MethodologyNote } from "@/components/track-record/MethodologyNote";
import { StatTiles } from "@/components/track-record/StatTiles";
import { TrackRecordTabs } from "@/components/track-record/TrackRecordTabs";
import { getTrackRecord } from "@/lib/track-record";
import { relativeTime } from "@/lib/relative-time";
```

- [ ] **Step 2: Replace the stacked detail sections with the tabs**

In the same file, replace the entire non-empty-branch block:

```tsx
            <div className="space-y-4">
              <StatTiles summary={tr.summary} />
              <div className="rounded-xl border border-line bg-card p-4">
                <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate/70">Cumulative R (all closed trades)</div>
                <EquityCurve points={tr.equity} />
              </div>
              <div className="grid gap-4 md:grid-cols-2">
                <Breakdown title="By strategy" rows={tr.byStrategy} />
                <Breakdown title="By symbol" rows={tr.bySymbol} />
              </div>
              <div className="rounded-xl border border-line bg-card p-4">
                <div className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-slate/70">Daily net (last ~13 weeks)</div>
                <Heatmap daily={tr.daily} />
              </div>
              <div className="rounded-xl border border-line bg-card p-4">
                <div className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-slate/70">Monthly P&amp;L (net R per day)</div>
                <PnLCalendar daily={tr.daily} />
              </div>
              <div className="rounded-xl border border-line bg-card p-4">
                <div className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-slate/70">Recent closed trades</div>
                <RecentTrades trades={tr.recent} />
              </div>
              <MethodologyNote />
            </div>
```

with:

```tsx
            <div className="space-y-4">
              <StatTiles summary={tr.summary} />
              <TrackRecordTabs
                equity={tr.equity}
                byStrategy={tr.byStrategy}
                bySymbol={tr.bySymbol}
                daily={tr.daily}
                recent={tr.recent}
              />
              <MethodologyNote />
            </div>
```

- [ ] **Step 3: Verify build**

Run: `cd web && npm run lint && npm run build`
Expected: build succeeds, `/track-record` still in the route list, and no unused-import lint errors (the five section imports are gone from the page). Pre-existing `@next/next/no-img-element` warnings are acceptable.

- [ ] **Step 4: Commit**

```bash
git add web/src/app/track-record/page.tsx
git commit -m "feat(track-record): tabbed layout on the page"
```

---

## Definition of Done

- `/track-record` shows the pinned stat tiles, then a 4-tab bar (Overview / Breakdown / Calendar / Trades); clicking a tab swaps the panel; the methodology note stays in the footer.
- `TrackRecordTabs` tab-switching is unit-tested (`npm test` green); `cd web && npm run build` succeeds; empty state unchanged.
