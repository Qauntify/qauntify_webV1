# Live Track-Record Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A public `/track-record` page that derives a full performance view (equity curve, win rate, expectancy, strategy/symbol breakdowns, daily heatmap, recent closed trades with outcome charts) browser-side from closed-signal rows.

**Architecture:** One anon RLS policy exposes terminal (closed) signals. A pure, unit-tested derivation layer (`web/src/lib/track-record.ts`) turns lean closed-signal rows into a `TrackRecord`. Server-component page + presentational components render it. No new server RPC.

**Tech Stack:** Next.js (pinned — see `web/AGENTS.md`), TypeScript, vitest, Supabase PostgREST + RLS, inline SVG charts, Tailwind.

---

## File Structure

**Create:**
- `web/src/lib/track-record.ts` — types + pure derivation functions + `getTrackRecord` fetch.
- `web/tests/lib/track-record.test.ts` — vitest unit tests for the pure functions.
- `web/src/lib/relative-time.ts` — `relativeTime(iso)` helper (shared by page + table).
- `web/src/components/track-record/{StatTiles,EquityCurve,Breakdown,Heatmap,RecentTrades,MethodologyNote}.tsx`.
- `web/src/app/track-record/page.tsx` — the public page.

**Modify:**
- `supabase/schema.sql` — anon closed-trade RLS policy.
- `web/src/components/shared/Nav.tsx` — add a "Track Record" nav link.

---

## Task 1: Anon RLS policy for closed trades

**Files:** Modify `supabase/schema.sql` (append at end)

- [ ] **Step 1: Append the policy**

Add to the end of `supabase/schema.sql`:

```sql
-- Public track record: let logged-out visitors read historical CLOSED trades
-- (non-actionable proof). Permissive RLS OR-combines with the 24h anon preview,
-- so open/live signals older than 24h stay hidden from anon.
drop policy if exists "anon closed-trade access" on public.signals;
create policy "anon closed-trade access"
    on public.signals for select
    to anon
    using (status in ('tp_hit', 'tp3_hit', 'sl_hit'));
```

- [ ] **Step 2: Apply it to Supabase**

Run the appended SQL in the Supabase SQL editor. Verify: as the anon role, `select count(*) from public.signals where status='sl_hit'` returns the full historical count (not just 24h).

- [ ] **Step 3: Commit**

```bash
git add supabase/schema.sql
git commit -m "feat(track-record): anon RLS policy for closed trades"
```

---

## Task 2: Derivation core + types + tests

**Files:**
- Create: `web/src/lib/track-record.ts`
- Test: `web/tests/lib/track-record.test.ts`

- [ ] **Step 1: Write the failing test**

Create `web/tests/lib/track-record.test.ts`:

```typescript
import { describe, it, expect } from "vitest";
import {
  tradeR, summarize, equityCurve, breakdown, dailyNet, recentTrades,
  toClosedTrade, type ClosedTrade,
} from "@/lib/track-record";

function trade(over: Partial<ClosedTrade> = {}): ClosedTrade {
  return {
    id: "x", symbol: "XAUUSD", timeframe: "5m", direction: "long",
    strategy: "ict_fvg", entry: 100, stopLoss: 98, target: 103,
    status: "tp3_hit", closedAt: "2026-07-01T00:00:00Z", outcomeChartUrl: null,
    ...over,
  };
}

describe("tradeR", () => {
  it("long win = |target-entry| / risk", () => {
    expect(tradeR(trade({ entry: 100, stopLoss: 98, target: 103, status: "tp3_hit" }))).toBeCloseTo(1.5);
  });
  it("short win uses absolute distances", () => {
    expect(tradeR(trade({ direction: "short", entry: 100, stopLoss: 102, target: 97, status: "tp3_hit" }))).toBeCloseTo(1.5);
  });
  it("legacy tp_hit uses its target", () => {
    expect(tradeR(trade({ entry: 100, stopLoss: 98, target: 102, status: "tp_hit" }))).toBeCloseTo(1);
  });
  it("sl_hit is -1R", () => {
    expect(tradeR(trade({ status: "sl_hit" }))).toBe(-1);
  });
  it("risk 0 guards to 0", () => {
    expect(tradeR(trade({ entry: 100, stopLoss: 100, status: "tp3_hit" }))).toBe(0);
  });
});

describe("summarize", () => {
  it("computes rate, netR, avg, streak, updatedAt", () => {
    const ts = [
      trade({ status: "tp3_hit", closedAt: "2026-07-01T00:00:00Z" }),
      trade({ status: "tp3_hit", closedAt: "2026-07-02T00:00:00Z" }),
      trade({ status: "sl_hit", closedAt: "2026-07-03T00:00:00Z" }),
    ];
    const s = summarize(ts);
    expect(s.total).toBe(3);
    expect(s.wins).toBe(2);
    expect(s.losses).toBe(1);
    expect(s.winRate).toBe(67);
    expect(s.netR).toBeCloseTo(2);
    expect(s.bestStreak).toBe(2);
    expect(s.updatedAt).toBe("2026-07-03T00:00:00Z");
  });
  it("empty -> zeros", () => {
    expect(summarize([])).toEqual({
      total: 0, wins: 0, losses: 0, winRate: 0, netR: 0, avgR: 0,
      bestStreak: 0, updatedAt: null,
    });
  });
});

describe("equityCurve", () => {
  it("cumulates in closed order regardless of input order", () => {
    const ts = [
      trade({ status: "sl_hit", closedAt: "2026-07-02T00:00:00Z" }),
      trade({ status: "tp3_hit", closedAt: "2026-07-01T00:00:00Z" }),
    ];
    expect(equityCurve(ts).map((p) => p.r)).toEqual([1.5, 0.5]);
  });
});

describe("breakdown", () => {
  it("groups + sorts by netR desc", () => {
    const ts = [
      trade({ strategy: "ict_fvg", status: "tp3_hit" }),
      trade({ strategy: "sr_zone", status: "sl_hit" }),
    ];
    const rows = breakdown(ts, (t) => t.strategy);
    expect(rows[0].name).toBe("ict_fvg");
    expect(rows[0].winRate).toBe(100);
    expect(rows[1].name).toBe("sr_zone");
    expect(rows[1].netR).toBe(-1);
  });
});

describe("dailyNet", () => {
  it("buckets R by calendar day", () => {
    const ts = [
      trade({ status: "tp3_hit", closedAt: "2026-07-01T05:00:00Z" }),
      trade({ status: "sl_hit", closedAt: "2026-07-01T09:00:00Z" }),
    ];
    expect(dailyNet(ts)).toEqual([{ date: "2026-07-01", net: 0.5 }]);
  });
});

describe("recentTrades + toClosedTrade", () => {
  it("recent sorts desc and slices", () => {
    const ts = [
      trade({ id: "a", closedAt: "2026-07-01T00:00:00Z" }),
      trade({ id: "b", closedAt: "2026-07-03T00:00:00Z" }),
    ];
    expect(recentTrades(ts, 1).map((t) => t.id)).toEqual(["b"]);
  });
  it("maps a raw row: target, closed_at fallback, strategy, chart url", () => {
    const t = toClosedTrade({
      id: "s1", symbol: "BTCUSD", timeframe: "15m", direction: "short",
      entry: 100, stop_loss: 102, take_profit: 96, take_profit_1: 98,
      take_profit_2: 96, take_profit_3: 94, status: "tp3_hit",
      created_at: "2026-07-01T00:00:00Z", closed_at: null,
      indicators: { strategy: "sr_zone" }, outcome_chart_url: "http://x.png",
    });
    expect(t?.target).toBe(94);
    expect(t?.closedAt).toBe("2026-07-01T00:00:00Z");
    expect(t?.strategy).toBe("sr_zone");
    expect(t?.outcomeChartUrl).toBe("http://x.png");
  });
  it("returns null for a non-terminal status", () => {
    expect(toClosedTrade({
      id: "s", symbol: "X", direction: "long", entry: 1, stop_loss: 1,
      created_at: "2026-07-01T00:00:00Z", status: "open",
    })).toBeNull();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npm test`
Expected: FAIL — cannot resolve `@/lib/track-record`.

- [ ] **Step 3: Write the implementation**

Create `web/src/lib/track-record.ts`:

```typescript
// Pure, browser-side derivation of the public track record from closed-signal
// rows. Every exported function below is pure (no network) so it is unit-tested
// directly; getTrackRecord (bottom) does the fetch.

export type ClosedStatus = "tp_hit" | "tp3_hit" | "sl_hit";

export type ClosedTrade = {
  id: string;
  symbol: string;
  timeframe: string;
  direction: "long" | "short";
  strategy: string;
  entry: number;
  stopLoss: number;
  target: number; // realized win-exit price (TP3, or legacy take_profit)
  status: ClosedStatus;
  closedAt: string; // closed_at ?? created_at
  outcomeChartUrl: string | null;
};

export type Summary = {
  total: number;
  wins: number;
  losses: number;
  winRate: number;
  netR: number;
  avgR: number;
  bestStreak: number;
  updatedAt: string | null;
};

export type EquityPoint = { t: string; r: number };
export type BreakdownRow = { name: string; winRate: number; netR: number; count: number };
export type DailyNet = { date: string; net: number };

export type TrackRecord = {
  summary: Summary;
  equity: EquityPoint[];
  byStrategy: BreakdownRow[];
  bySymbol: BreakdownRow[];
  byTimeframe: BreakdownRow[];
  daily: DailyNet[];
  recent: ClosedTrade[];
};

const round1 = (n: number) => Math.round(n * 10) / 10;
const round2 = (n: number) => Math.round(n * 100) / 100;

const WIN = new Set<ClosedStatus>(["tp_hit", "tp3_hit"]);
export function isWin(t: ClosedTrade): boolean {
  return WIN.has(t.status);
}

export function tradeR(t: ClosedTrade): number {
  const risk = Math.abs(t.entry - t.stopLoss);
  if (risk === 0) return 0;
  if (t.status === "sl_hit") return -1;
  return Math.abs(t.target - t.entry) / risk;
}

function byClosedAsc(a: ClosedTrade, b: ClosedTrade): number {
  return a.closedAt.localeCompare(b.closedAt);
}

export function summarize(trades: ClosedTrade[]): Summary {
  const total = trades.length;
  const wins = trades.filter(isWin).length;
  const netR = trades.reduce((s, t) => s + tradeR(t), 0);
  const sorted = [...trades].sort(byClosedAsc);
  let bestStreak = 0;
  let cur = 0;
  for (const t of sorted) {
    if (isWin(t)) {
      cur += 1;
      bestStreak = Math.max(bestStreak, cur);
    } else {
      cur = 0;
    }
  }
  return {
    total,
    wins,
    losses: total - wins,
    winRate: total ? Math.round((wins / total) * 100) : 0,
    netR: round1(netR),
    avgR: total ? round2(netR / total) : 0,
    bestStreak,
    updatedAt: sorted.length ? sorted[sorted.length - 1].closedAt : null,
  };
}

export function equityCurve(trades: ClosedTrade[]): EquityPoint[] {
  let cum = 0;
  return [...trades].sort(byClosedAsc).map((t) => {
    cum += tradeR(t);
    return { t: t.closedAt, r: round2(cum) };
  });
}

export function breakdown(
  trades: ClosedTrade[],
  keyOf: (t: ClosedTrade) => string,
): BreakdownRow[] {
  const groups = new Map<string, ClosedTrade[]>();
  for (const t of trades) {
    const k = keyOf(t) || "—";
    const list = groups.get(k);
    if (list) list.push(t);
    else groups.set(k, [t]);
  }
  return [...groups.entries()]
    .map(([name, ts]) => ({
      name,
      count: ts.length,
      winRate: Math.round((ts.filter(isWin).length / ts.length) * 100),
      netR: round1(ts.reduce((s, t) => s + tradeR(t), 0)),
    }))
    .sort((a, b) => b.netR - a.netR);
}

export function dailyNet(trades: ClosedTrade[]): DailyNet[] {
  const m = new Map<string, number>();
  for (const t of trades) {
    const date = t.closedAt.slice(0, 10);
    m.set(date, (m.get(date) ?? 0) + tradeR(t));
  }
  return [...m.entries()]
    .map(([date, net]) => ({ date, net: round2(net) }))
    .sort((a, b) => a.date.localeCompare(b.date));
}

export function recentTrades(trades: ClosedTrade[], n: number): ClosedTrade[] {
  return [...trades].sort((a, b) => b.closedAt.localeCompare(a.closedAt)).slice(0, n);
}

type RawRow = {
  id: string;
  symbol: string;
  timeframe?: string | null;
  direction: string;
  entry: number;
  stop_loss: number;
  take_profit?: number | null;
  take_profit_1?: number | null;
  take_profit_2?: number | null;
  take_profit_3?: number | null;
  status?: string;
  created_at: string;
  closed_at?: string | null;
  indicators?: Record<string, unknown> | null;
  outcome_chart_url?: string | null;
};

export function toClosedTrade(row: RawRow): ClosedTrade | null {
  const status = row.status;
  if (status !== "tp_hit" && status !== "tp3_hit" && status !== "sl_hit") return null;
  const ind: Record<string, unknown> = row.indicators ?? {};
  const strategy =
    typeof ind.strategy === "string"
      ? (ind.strategy as string)
      : "ema9" in ind
        ? "ema_cross"
        : "—";
  const target =
    status === "tp_hit"
      ? Number(row.take_profit)
      : Number(row.take_profit_3 ?? row.take_profit_1 ?? row.take_profit);
  return {
    id: row.id,
    symbol: row.symbol,
    timeframe: row.timeframe ?? "—",
    direction: row.direction === "short" ? "short" : "long",
    strategy,
    entry: Number(row.entry),
    stopLoss: Number(row.stop_loss),
    target,
    status,
    closedAt: typeof row.closed_at === "string" ? row.closed_at : row.created_at,
    outcomeChartUrl: typeof row.outcome_chart_url === "string" ? row.outcome_chart_url : null,
  };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npm test`
Expected: PASS (all `track-record.test.ts` cases).

- [ ] **Step 5: Commit**

```bash
git add web/src/lib/track-record.ts web/tests/lib/track-record.test.ts
git commit -m "feat(track-record): pure derivation functions + tests"
```

---

## Task 3: getTrackRecord fetch wrapper

**Files:** Modify `web/src/lib/track-record.ts` (append)

- [ ] **Step 1: Append the fetch + assembler**

Add to the END of `web/src/lib/track-record.ts`:

```typescript
async function fetchClosedRows(accessToken?: string): Promise<RawRow[] | null> {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !anonKey) return null;
  const base = url.replace(/\/$/, "");
  const query =
    "select=id,symbol,timeframe,direction,entry,stop_loss,take_profit," +
    "take_profit_1,take_profit_2,take_profit_3,status,created_at,closed_at," +
    "indicators,outcome_chart_url" +
    "&status=in.(tp_hit,tp3_hit,sl_hit)&order=closed_at.asc.nullslast";
  try {
    const res = await fetch(`${base}/rest/v1/signals?${query}`, {
      headers: { apikey: anonKey, Authorization: `Bearer ${accessToken ?? anonKey}` },
      cache: "no-store",
    });
    if (!res.ok) return null;
    const rows = await res.json();
    return Array.isArray(rows) ? (rows as RawRow[]) : null;
  } catch {
    return null;
  }
}

export async function getTrackRecord(accessToken?: string): Promise<TrackRecord> {
  const rows = await fetchClosedRows(accessToken);
  const trades = (rows ?? [])
    .map(toClosedTrade)
    .filter((t): t is ClosedTrade => t !== null);
  return {
    summary: summarize(trades),
    equity: equityCurve(trades),
    byStrategy: breakdown(trades, (t) => t.strategy),
    bySymbol: breakdown(trades, (t) => t.symbol),
    byTimeframe: breakdown(trades, (t) => t.timeframe),
    daily: dailyNet(trades),
    recent: recentTrades(trades, 20),
  };
}
```

- [ ] **Step 2: Verify types compile + tests still pass**

Run: `cd web && npx tsc --noEmit && npm test`
Expected: no type errors; tests still green.

- [ ] **Step 3: Commit**

```bash
git add web/src/lib/track-record.ts
git commit -m "feat(track-record): getTrackRecord fetch wrapper"
```

---

## Task 4: Presentational components

**Files:**
- Create: `web/src/lib/relative-time.ts`
- Create: `web/src/components/track-record/StatTiles.tsx`, `EquityCurve.tsx`, `Breakdown.tsx`, `Heatmap.tsx`, `RecentTrades.tsx`, `MethodologyNote.tsx`

**Before writing:** read `web/AGENTS.md` (pinned Next.js). These are server components (no hooks/handlers). Win/loss colors use Tailwind `emerald-400`/`rose-400`; layout uses the existing theme tokens (`bg-card`, `border-line`, `text-ink`, `text-slate`) seen in `Nav.tsx`/`SignalsGrid.tsx`. The `<img>` in `RecentTrades` will emit the expected `@next/next/no-img-element` lint warning — that is acceptable (matches the setup/outcome chart images).

- [ ] **Step 1: Create the relative-time helper**

Create `web/src/lib/relative-time.ts`:

```typescript
export function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const h = Math.floor(diff / 3.6e6);
  if (h < 1) return "just now";
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  return d === 1 ? "yesterday" : `${d}d ago`;
}
```

- [ ] **Step 2: Create `StatTiles.tsx`**

```tsx
import type { Summary } from "@/lib/track-record";

export function StatTiles({ summary }: { summary: Summary }) {
  const tone = (n: number) => (n >= 0 ? "text-emerald-400" : "text-rose-400");
  const tiles = [
    { label: "Win rate", value: `${summary.winRate}%`, sub: `${summary.wins} / ${summary.total} closed`, cls: "text-emerald-400" },
    { label: "Net R", value: `${summary.netR >= 0 ? "+" : ""}${summary.netR}R`, sub: `across ${summary.total} trades`, cls: tone(summary.netR) },
    { label: "Avg / trade", value: `${summary.avgR >= 0 ? "+" : ""}${summary.avgR}R`, sub: "expectancy", cls: tone(summary.avgR) },
    { label: "Best streak", value: `${summary.bestStreak}`, sub: "wins in a row", cls: "text-ink" },
  ];
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
      {tiles.map((t) => (
        <div key={t.label} className="rounded-xl border border-line bg-card p-4">
          <div className="text-[10px] font-semibold uppercase tracking-wider text-slate/70">{t.label}</div>
          <div className={`mt-1 text-2xl font-extrabold ${t.cls}`}>{t.value}</div>
          <div className="mt-0.5 text-[11px] text-slate/70">{t.sub}</div>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 3: Create `EquityCurve.tsx`**

```tsx
import type { EquityPoint } from "@/lib/track-record";

export function EquityCurve({ points }: { points: EquityPoint[] }) {
  if (points.length < 2) {
    return <div className="text-sm text-slate/60">Not enough closed trades yet to plot an equity curve.</div>;
  }
  const W = 720;
  const H = 160;
  const pad = 6;
  const rs = points.map((p) => p.r);
  const max = Math.max(...rs, 0);
  const min = Math.min(...rs, 0);
  const span = max - min || 1;
  const x = (i: number) => pad + (i / (points.length - 1)) * (W - 2 * pad);
  const y = (r: number) => H - pad - ((r - min) / span) * (H - 2 * pad);
  const line = points.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p.r).toFixed(1)}`).join(" ");
  const area = `${line} L${x(points.length - 1).toFixed(1)},${(H - pad).toFixed(1)} L${x(0).toFixed(1)},${(H - pad).toFixed(1)} Z`;
  const stroke = points[points.length - 1].r >= 0 ? "#34d399" : "#fb7185";
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="Cumulative R equity curve">
      <defs>
        <linearGradient id="eq-grad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor={stroke} stopOpacity="0.25" />
          <stop offset="1" stopColor={stroke} stopOpacity="0" />
        </linearGradient>
      </defs>
      <line x1={pad} y1={y(0)} x2={W - pad} y2={y(0)} stroke="rgba(148,163,184,.3)" strokeDasharray="3 3" />
      <path d={area} fill="url(#eq-grad)" />
      <path d={line} fill="none" stroke={stroke} strokeWidth="2" />
    </svg>
  );
}
```

- [ ] **Step 4: Create `Breakdown.tsx`**

```tsx
import type { BreakdownRow } from "@/lib/track-record";

export function Breakdown({ title, rows }: { title: string; rows: BreakdownRow[] }) {
  return (
    <div className="rounded-xl border border-line bg-card p-4">
      <div className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-slate/70">{title}</div>
      {rows.length === 0 ? (
        <div className="text-sm text-slate/60">No data yet.</div>
      ) : (
        rows.map((r) => (
          <div key={r.name} className="mb-2.5">
            <div className="mb-1 flex justify-between text-xs">
              <span className="text-ink">{r.name}</span>
              <span className="text-slate/70">
                {r.winRate}% · <b className={r.netR >= 0 ? "text-emerald-400" : "text-rose-400"}>{r.netR >= 0 ? "+" : ""}{r.netR}R</b>
              </span>
            </div>
            <div className="h-1.5 overflow-hidden rounded bg-slate/15">
              <div className={`h-full ${r.winRate >= 50 ? "bg-emerald-400" : "bg-rose-400"}`} style={{ width: `${r.winRate}%` }} />
            </div>
          </div>
        ))
      )}
    </div>
  );
}
```

- [ ] **Step 5: Create `Heatmap.tsx`**

```tsx
import type { DailyNet } from "@/lib/track-record";

export function Heatmap({ daily }: { daily: DailyNet[] }) {
  const recent = daily.slice(-91);
  if (recent.length === 0) return <div className="text-sm text-slate/60">No closed days yet.</div>;
  return (
    <div className="flex flex-wrap gap-[3px]">
      {recent.map((d) => {
        const color = d.net > 0 ? "bg-emerald-400" : d.net < 0 ? "bg-rose-400" : "bg-slate/20";
        const opacity = d.net === 0 ? 0.4 : Math.min(1, 0.4 + Math.abs(d.net) / 4);
        return (
          <div
            key={d.date}
            title={`${d.date}: ${d.net >= 0 ? "+" : ""}${d.net}R`}
            className={`h-3.5 w-3.5 rounded-[3px] ${color}`}
            style={{ opacity }}
          />
        );
      })}
    </div>
  );
}
```

- [ ] **Step 6: Create `RecentTrades.tsx`**

```tsx
import type { ClosedTrade } from "@/lib/track-record";
import { relativeTime } from "@/lib/relative-time";

export function RecentTrades({ trades }: { trades: ClosedTrade[] }) {
  if (trades.length === 0) return <div className="text-sm text-slate/60">No closed trades yet.</div>;
  return (
    <div className="divide-y divide-line/60">
      {trades.map((t) => {
        const win = t.status === "tp3_hit" || t.status === "tp_hit";
        return (
          <div key={t.id} className="grid grid-cols-[auto_1fr_auto_auto] items-center gap-3 py-2 text-sm">
            {t.outcomeChartUrl ? (
              <a href={t.outcomeChartUrl} target="_blank" rel="noopener noreferrer">
                <img src={t.outcomeChartUrl} alt={`${t.symbol} outcome`} loading="lazy" className="h-8 w-14 rounded border border-line object-cover" />
              </a>
            ) : (
              <div className="h-8 w-14 rounded border border-line bg-slate/10" />
            )}
            <div>
              <span className="font-semibold text-ink">{t.symbol}</span>{" "}
              <span className="text-slate/60">{t.timeframe}</span>{" "}
              <span className={t.direction === "long" ? "text-emerald-400" : "text-rose-400"}>{t.direction.toUpperCase()}</span>
            </div>
            <div className={`text-xs font-bold ${win ? "text-emerald-400" : "text-rose-400"}`}>{win ? "✓ TP3" : "✗ SL"}</div>
            <div className="text-right text-slate/60">{relativeTime(t.closedAt)}</div>
          </div>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 7: Create `MethodologyNote.tsx`**

```tsx
export function MethodologyNote() {
  return (
    <p className="mt-4 text-[11px] leading-relaxed text-slate/60">
      R = reward ÷ risk. A stop-loss counts as −1R; a full TP3 win counts at its target R. Partial exits are counted conservatively. Every closed signal is shown — nothing cherry-picked. Past performance is not financial advice.
    </p>
  );
}
```

- [ ] **Step 8: Type-check**

Run: `cd web && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 9: Commit**

```bash
git add web/src/lib/relative-time.ts web/src/components/track-record
git commit -m "feat(track-record): presentational components"
```

---

## Task 5: The page

**Files:** Create `web/src/app/track-record/page.tsx`

- [ ] **Step 1: Create the page**

Create `web/src/app/track-record/page.tsx`:

```tsx
import { Footer } from "@/components/shared/Footer";
import { Nav } from "@/components/shared/Nav";
import { Breakdown } from "@/components/track-record/Breakdown";
import { EquityCurve } from "@/components/track-record/EquityCurve";
import { Heatmap } from "@/components/track-record/Heatmap";
import { MethodologyNote } from "@/components/track-record/MethodologyNote";
import { RecentTrades } from "@/components/track-record/RecentTrades";
import { StatTiles } from "@/components/track-record/StatTiles";
import { getTrackRecord } from "@/lib/track-record";
import { relativeTime } from "@/lib/relative-time";

export const revalidate = 60;

export const metadata = {
  title: "Live Track Record — Qauntify",
  description: "Every signal, wins and losses. Real, auto-updated performance.",
};

export default async function TrackRecordPage() {
  const tr = await getTrackRecord();
  const empty = tr.summary.total === 0;
  return (
    <>
      <Nav />
      <main className="flex-1">
        <section className="page-container py-10">
          <div className="mb-6 flex items-end justify-between gap-4">
            <div>
              <h1 className="text-2xl font-extrabold text-ink md:text-3xl">Live Track Record</h1>
              <p className="mt-1 text-sm text-slate/70">Every signal — wins and losses. Nothing cherry-picked.</p>
            </div>
            {tr.summary.updatedAt ? (
              <span className="whitespace-nowrap rounded-full border border-line px-3 py-1 text-[11px] text-slate/60">● updated {relativeTime(tr.summary.updatedAt)}</span>
            ) : null}
          </div>

          {empty ? (
            <div className="rounded-xl border border-line bg-card p-10 text-center text-slate/70">
              Your track record fills in as trades close. Check back soon.
            </div>
          ) : (
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
                <div className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-slate/70">Recent closed trades</div>
                <RecentTrades trades={tr.recent} />
              </div>
              <MethodologyNote />
            </div>
          )}
        </section>
      </main>
      <Footer />
    </>
  );
}
```

- [ ] **Step 2: Verify build**

Run: `cd web && npm run lint && npm run build`
Expected: build succeeds; `/track-record` appears in the route list. A `@next/next/no-img-element` warning on `RecentTrades` is acceptable. Confirm the page renders (empty-state if the DB has no closed signals yet).

- [ ] **Step 3: Commit**

```bash
git add web/src/app/track-record/page.tsx
git commit -m "feat(track-record): public /track-record page"
```

---

## Task 6: Nav link

**Files:** Modify `web/src/components/shared/Nav.tsx`

- [ ] **Step 1: Add the link**

In `web/src/components/shared/Nav.tsx`, add a "Track Record" entry to the `links` array (place it after the War Room entry):

```typescript
  { href: "/war-room", label: "War Room" },
  { href: "/track-record", label: "Track Record" },
```

- [ ] **Step 2: Verify build**

Run: `cd web && npm run build`
Expected: build succeeds; the nav shows a "Track Record" link pointing to `/track-record`.

- [ ] **Step 3: Commit**

```bash
git add web/src/components/shared/Nav.tsx
git commit -m "feat(track-record): link the page from the nav"
```

---

## Definition of Done

- `/track-record` is public and shows equity curve, stat tiles, strategy/symbol breakdowns, daily heatmap, and recent closed trades (with outcome-chart thumbnails), all derived from closed-signal rows.
- Logged-out visitors can read closed trades (anon RLS policy) but not older open signals.
- All derivation functions are unit-tested (`npm test` green); `cd web && npm run build` succeeds.
- Empty DB → friendly empty state, no broken charts.
