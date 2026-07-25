# Monthly P&L Calendar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a monthly calendar section to `/track-record` showing net R per day (green up / red down), fed by the daily-R data the page already derives.

**Architecture:** A pure, tested `buildMonthGrid` helper builds the Monday-start month grid; a client `PnLCalendar` component renders it with month navigation and looks up each day's net R from the page's `tr.daily`; the page adds one card section. The admin calendar is untouched.

**Tech Stack:** Next.js (pinned — see `web/AGENTS.md`), TypeScript, vitest, Tailwind.

---

## File Structure

**Create:**
- `web/src/lib/month-grid.ts` — `buildMonthGrid(year, month)` (pure).
- `web/tests/lib/month-grid.test.ts` — vitest tests.
- `web/src/components/track-record/PnLCalendar.tsx` — client calendar component.

**Modify:**
- `web/src/app/track-record/page.tsx` — add the "Monthly P&L" card.

---

## Task 1: month-grid helper + tests

**Files:**
- Create: `web/src/lib/month-grid.ts`
- Test: `web/tests/lib/month-grid.test.ts`

- [ ] **Step 1: Write the failing test**

Create `web/tests/lib/month-grid.test.ts`:

```typescript
import { describe, it, expect } from "vitest";
import { buildMonthGrid } from "@/lib/month-grid";

describe("buildMonthGrid", () => {
  it("Monday-start month with no padding (Feb 2021 starts Monday)", () => {
    const cells = buildMonthGrid(2021, 1); // month is 0-indexed -> Feb
    expect(cells.length).toBe(28);
    expect(cells[0]).toEqual({ dateStr: "2021-02-01", dayNum: 1, inMonth: true });
    expect(cells[27]).toEqual({ dateStr: "2021-02-28", dayNum: 28, inMonth: true });
    expect(cells.filter((c) => c.inMonth).length).toBe(28);
  });

  it("pads leading + trailing to full weeks (Aug 2021 starts Sunday)", () => {
    const cells = buildMonthGrid(2021, 7); // Aug
    expect(cells.length % 7).toBe(0);
    expect(cells.length).toBe(42);
    expect(cells[0]).toEqual({ dateStr: "2021-07-26", dayNum: 26, inMonth: false });
    const firstInMonth = cells.find((c) => c.inMonth)!;
    expect(firstInMonth.dateStr).toBe("2021-08-01");
    expect(cells.filter((c) => c.inMonth).length).toBe(31);
    expect(cells[cells.length - 1].inMonth).toBe(false);
  });

  it("leading padding crosses the year boundary (Jan 2021 leads from Dec 2020)", () => {
    const cells = buildMonthGrid(2021, 0); // Jan 2021, the 1st is a Friday
    const firstInMonthIdx = cells.findIndex((c) => c.inMonth);
    expect(firstInMonthIdx).toBe(4); // Mon..Thu from December
    expect(cells.slice(0, firstInMonthIdx).every((c) => c.dateStr.startsWith("2020-12"))).toBe(true);
    expect(cells[0].dateStr).toBe("2020-12-28");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npm test`
Expected: FAIL — cannot resolve `@/lib/month-grid`.

- [ ] **Step 3: Write the implementation**

Create `web/src/lib/month-grid.ts`:

```typescript
export type MonthCell = { dateStr: string; dayNum: number; inMonth: boolean };

function iso(year: number, month0: number, day: number): string {
  const mm = String(month0 + 1).padStart(2, "0");
  const dd = String(day).padStart(2, "0");
  return `${year}-${mm}-${dd}`;
}

// Monday-start calendar grid for `month` (0-11), padded with the tail of the
// previous month and the head of the next month so it fills whole weeks.
// dateStr is formatted from the integer date parts (no Date timezone
// conversion) so it compares directly against dailyNet's date keys.
export function buildMonthGrid(year: number, month: number): MonthCell[] {
  const firstDow = new Date(year, month, 1).getDay(); // 0=Sun..6=Sat
  const lead = (firstDow + 6) % 7; // days shown before the 1st (Monday start)
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const daysInPrev = new Date(year, month, 0).getDate();
  const prevMonth = month === 0 ? 11 : month - 1;
  const prevYear = month === 0 ? year - 1 : year;
  const nextMonth = month === 11 ? 0 : month + 1;
  const nextYear = month === 11 ? year + 1 : year;

  const cells: MonthCell[] = [];
  for (let i = lead - 1; i >= 0; i--) {
    const day = daysInPrev - i;
    cells.push({ dateStr: iso(prevYear, prevMonth, day), dayNum: day, inMonth: false });
  }
  for (let day = 1; day <= daysInMonth; day++) {
    cells.push({ dateStr: iso(year, month, day), dayNum: day, inMonth: true });
  }
  const trail = (7 - (cells.length % 7)) % 7;
  for (let day = 1; day <= trail; day++) {
    cells.push({ dateStr: iso(nextYear, nextMonth, day), dayNum: day, inMonth: false });
  }
  return cells;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npm test`
Expected: PASS (the 3 new month-grid cases + all existing web tests).

- [ ] **Step 5: Commit**

```bash
git add web/src/lib/month-grid.ts web/tests/lib/month-grid.test.ts
git commit -m "feat(track-record): tested month-grid helper"
```

---

## Task 2: PnLCalendar component

**Files:**
- Create: `web/src/components/track-record/PnLCalendar.tsx`

**Before writing:** read `web/AGENTS.md` (pinned Next.js). This is a client component (`"use client"`, uses `useState`/`useMemo`). It takes `DailyNet[]` (`{ date: string; net: number }`) — the type is exported from `@/lib/track-record`. Win/loss colors: `emerald-400` / `rose-400`; layout tokens `bg-card`, `border-line`, `text-ink`, `text-slate`.

- [ ] **Step 1: Create the component**

Create `web/src/components/track-record/PnLCalendar.tsx`:

```tsx
"use client";

import { useMemo, useState } from "react";
import { buildMonthGrid } from "@/lib/month-grid";
import type { DailyNet } from "@/lib/track-record";

const DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export function PnLCalendar({ daily }: { daily: DailyNet[] }) {
  const netByDate = useMemo(() => {
    const m = new Map<string, number>();
    for (const d of daily) m.set(d.date, d.net);
    return m;
  }, [daily]);

  const latest = daily.length ? daily[daily.length - 1].date : null;

  const [ym, setYm] = useState<{ y: number; m: number }>(() => {
    if (latest) {
      const [y, m] = latest.split("-").map(Number);
      return { y, m: m - 1 };
    }
    const now = new Date();
    return { y: now.getFullYear(), m: now.getMonth() };
  });

  const shift = (delta: number) =>
    setYm(({ y, m }) => {
      const t = y * 12 + m + delta;
      return { y: Math.floor(t / 12), m: ((t % 12) + 12) % 12 };
    });

  const jumpLatest = () => {
    if (!latest) return;
    const [y, m] = latest.split("-").map(Number);
    setYm({ y, m: m - 1 });
  };

  const monthName = new Date(ym.y, ym.m, 1).toLocaleString("default", { month: "long" });
  const cells = useMemo(() => buildMonthGrid(ym.y, ym.m), [ym]);

  return (
    <div>
      <div className="mb-3 flex items-center justify-center gap-3">
        <button onClick={() => shift(-1)} aria-label="Previous month" className="px-2 text-lg leading-none text-slate hover:text-ink">‹</button>
        <span className="min-w-[150px] text-center text-sm font-bold text-ink">{monthName} {ym.y}</span>
        <button onClick={() => shift(1)} aria-label="Next month" className="px-2 text-lg leading-none text-slate hover:text-ink">›</button>
        {latest ? (
          <button onClick={jumpLatest} className="text-[11px] text-slate hover:text-ink">latest</button>
        ) : null}
      </div>
      <div className="overflow-x-auto">
        <div className="min-w-[560px]">
          <div className="mb-1 grid grid-cols-7">
            {DOW.map((d) => (
              <div key={d} className="text-center text-[11px] font-semibold text-slate/70">{d}</div>
            ))}
          </div>
          <div className="grid grid-cols-7 gap-1.5">
            {cells.map((c) => {
              const net = c.inMonth ? netByDate.get(c.dateStr) : undefined;
              let tone = "bg-card border-line";
              if (net !== undefined) {
                tone =
                  net > 0
                    ? "bg-emerald-400/15 border-emerald-400/40"
                    : net < 0
                      ? "bg-rose-400/15 border-rose-400/40"
                      : "bg-slate/15 border-slate/30";
              }
              return (
                <div
                  key={c.dateStr}
                  className={`flex h-16 flex-col rounded-md border p-1.5 ${tone} ${c.inMonth ? "" : "opacity-40"}`}
                >
                  <span className="text-[11px] font-semibold text-slate/80">{c.dayNum}</span>
                  {net !== undefined ? (
                    <span className={`mt-auto text-right text-xs font-bold ${net >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                      {net >= 0 ? "+" : ""}{net}R
                    </span>
                  ) : null}
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Type-check**

Run: `cd web && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add web/src/components/track-record/PnLCalendar.tsx
git commit -m "feat(track-record): net-R monthly P&L calendar component"
```

---

## Task 3: Wire the section into the page

**Files:**
- Modify: `web/src/app/track-record/page.tsx`

- [ ] **Step 1: Add the import**

In `web/src/app/track-record/page.tsx`, add this import alongside the other `@/components/track-record/*` imports:

```tsx
import { PnLCalendar } from "@/components/track-record/PnLCalendar";
```

- [ ] **Step 2: Add the section**

Find the existing daily-heatmap card:

```tsx
              <div className="rounded-xl border border-line bg-card p-4">
                <div className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-slate/70">Daily net (last ~13 weeks)</div>
                <Heatmap daily={tr.daily} />
              </div>
```

Immediately AFTER that closing `</div>`, insert:

```tsx
              <div className="rounded-xl border border-line bg-card p-4">
                <div className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-slate/70">Monthly P&amp;L (net R per day)</div>
                <PnLCalendar daily={tr.daily} />
              </div>
```

- [ ] **Step 3: Verify build**

Run: `cd web && npm run lint && npm run build`
Expected: build succeeds; `/track-record` still in the route list. Any pre-existing `@next/next/no-img-element` warnings are unrelated/acceptable.

- [ ] **Step 4: Commit**

```bash
git add web/src/app/track-record/page.tsx
git commit -m "feat(track-record): add Monthly P&L calendar section"
```

---

## Definition of Done

- `/track-record` shows a "Monthly P&L (net R per day)" calendar with month navigation; each day with trades is tinted green/red and shows its signed net R; empty days are blank.
- `buildMonthGrid` is unit-tested (`npm test` green); `cd web && npm run build` succeeds.
- The admin `DailyPnLCalendar` is unchanged.
