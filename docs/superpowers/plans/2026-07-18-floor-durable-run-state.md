# Trading Floor Durable Run State Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the Gold AI hunter's run/stop state out of fragile in-process memory and into Supabase, replacing the internal infinite loop with one cycle per invocation driven by an external cron (+ GitHub Actions backup), so "Run" genuinely persists until "Stop" on Vercel's serverless platform.

**Architecture:** A new single-row `floor_run_state` Supabase table becomes the only source of truth for `enabled`/`in_progress`/`cycle`/`phase`/`lastMessage`/`lastSignal`. `run-control.ts` is rewritten from a module-level singleton to a set of functions issuing REST calls against that table (same raw-fetch pattern `store.ts` already uses for `floor_briefs`). `gold-cycle.ts` drops its internal `while`/sleep loop; a new `runOneGoldCycleIfEnabled()` runs exactly one cycle, guarded by an atomic compare-and-swap PATCH so a manual "Run now" and a cron tick can never overlap. Both the admin Run button and the cron endpoint call this same function.

**Tech Stack:** Next.js 16 App Router route handlers, Supabase Postgres (REST/PostgREST), Vitest, GitHub Actions.

**Reference:** `docs/superpowers/specs/2026-07-18-floor-durable-run-state-design.md`

---

### Task 1: Supabase migration — `floor_run_state`

**Files:**
- Create: `supabase/migrations/20260718_floor_run_state.sql`

- [ ] **Step 1: Write the migration**

```sql
-- Durable run state for the trading floor's Gold AI hunter.
-- Single source of truth for whether the hunter is enabled, whether a
-- cycle is currently executing, and the latest cycle/phase/message/signal
-- — replaces module-level in-memory state, which Vercel's serverless
-- model doesn't guarantee survives past a single response.
create table if not exists public.floor_run_state (
    id int primary key default 1,
    enabled boolean not null default false,
    in_progress boolean not null default false,
    run_id text,
    cycle int not null default 0,
    phase text not null default 'idle',
    last_message text not null default '',
    last_signal jsonb,
    updated_at timestamptz not null default now(),
    constraint floor_run_state_singleton check (id = 1)
);

insert into public.floor_run_state (id) values (1)
    on conflict (id) do nothing;

alter table public.floor_run_state enable row level security;

drop policy if exists "members read floor run state" on public.floor_run_state;
create policy "members read floor run state"
    on public.floor_run_state for select
    to authenticated
    using (true);
```

- [ ] **Step 2: Apply the migration**

Run this SQL in the Supabase SQL editor (Dashboard → SQL Editor) for the
project this app points at. Confirm it worked:

```sql
select * from public.floor_run_state;
```

Expected: one row, `id=1`, `enabled=false`, `in_progress=false`, `cycle=0`,
`phase='idle'`, `last_message=''`, `last_signal=null`.

- [ ] **Step 3: Commit**

```bash
git add supabase/migrations/20260718_floor_run_state.sql
git commit -m "Add floor_run_state table for durable trading-floor run state"
```

---

### Task 2: Shared Supabase config helper (DRY, no behavior change)

**Files:**
- Create: `web/src/lib/floor/supabase-config.ts`
- Modify: `web/src/lib/floor/store.ts`

`store.ts` and the rewritten `run-control.ts` (Task 4) both need the same
"read Supabase URL + service-role key from env" logic. Extracting it now
avoids duplicating it a second time in Task 4.

- [ ] **Step 1: Create the shared helper**

```ts
// web/src/lib/floor/supabase-config.ts
export type FloorSupabaseConfig = { url: string; serviceKey: string };

export function floorSupabaseConfig(): FloorSupabaseConfig | null {
  const url = (process.env.NEXT_PUBLIC_SUPABASE_URL || process.env.SUPABASE_URL)?.trim();
  const serviceKey = process.env.SUPABASE_SERVICE_ROLE_KEY?.trim();
  if (!url || !serviceKey) return null;
  return { url: url.replace(/\/$/, ""), serviceKey };
}

export function floorSupabaseHeaders(serviceKey: string): HeadersInit {
  return {
    apikey: serviceKey,
    Authorization: `Bearer ${serviceKey}`,
    "Content-Type": "application/json",
  };
}
```

- [ ] **Step 2: Update `store.ts` to use it**

Replace the top of `web/src/lib/floor/store.ts` (the local `config()` and
`headers()` functions, and their usage in `insertFloorBrief`) so the file
reads:

```ts
import type { FloorDesk, FloorTone } from "./types";
import { floorSupabaseConfig, floorSupabaseHeaders } from "./supabase-config";

export async function insertFloorBrief(input: {
  desk: FloorDesk;
  tone: FloorTone;
  body: string;
  runId: string;
}): Promise<void> {
  const cfg = floorSupabaseConfig();
  if (!cfg) throw new Error("Supabase service-role configuration is unavailable");

  const response = await fetch(`${cfg.url}/rest/v1/floor_briefs`, {
    method: "POST",
    headers: { ...floorSupabaseHeaders(cfg.serviceKey), Prefer: "return=minimal" },
    body: JSON.stringify({
      desk: input.desk,
      tone: input.tone,
      body: input.body,
      run_id: input.runId,
    }),
  });
  if (!response.ok) {
    throw new Error(`Could not insert floor brief (HTTP ${response.status})`);
  }
}
```

- [ ] **Step 3: Typecheck**

Run: `cd web && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add web/src/lib/floor/supabase-config.ts web/src/lib/floor/store.ts
git commit -m "Extract shared Supabase config helper from store.ts"
```

---

### Task 3: Drop `log` from `FloorRunStatus`

**Files:**
- Modify: `web/src/lib/floor/types.ts:56-64`

The admin log stream will read from `floor_briefs` (already durable, same
as the public board) instead of an in-memory copy, so `FloorRunStatus` no
longer needs a `log` field. `FloorLogEntry` itself stays — it's still the
shape of `floor_briefs`-derived log entries used by the board response.

- [ ] **Step 1: Edit the type**

In `web/src/lib/floor/types.ts`, change:

```ts
export type FloorRunStatus = {
  running: boolean;
  runId: string | null;
  cycle: number;
  phase: FloorRunPhase;
  lastMessage: string;
  lastSignal: FloorGoldSignal | null;
  log: FloorLogEntry[];
};
```

to:

```ts
export type FloorRunStatus = {
  running: boolean;
  runId: string | null;
  cycle: number;
  phase: FloorRunPhase;
  lastMessage: string;
  lastSignal: FloorGoldSignal | null;
};
```

- [ ] **Step 2: Commit**

This will show as a type error alongside not-yet-updated consumers until
Tasks 4–7 land — that's expected. Just commit the type change now:

```bash
git add web/src/lib/floor/types.ts
git commit -m "Drop log field from FloorRunStatus (moves to floor_briefs)"
```

---

### Task 4: Rewrite `run-control.ts` as Supabase-backed (TDD)

**Files:**
- Modify: `web/src/lib/floor/run-control.ts` (full rewrite)
- Test: `web/src/lib/floor/run-control.test.ts` (full rewrite)

This is the core of the feature: replacing the in-memory singleton with
REST calls against `floor_run_state`. `armFloorRun` and `beginCycle` use an
atomic compare-and-swap PATCH (a `WHERE`-clause filter on the *current*
state, e.g. `enabled=eq.false`) so two overlapping invocations — a manual
"Run now" landing at the same instant as a cron tick — can never both
succeed.

- [ ] **Step 1: Write the failing test**

Replace the entire contents of `web/src/lib/floor/run-control.test.ts`:

```ts
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  armFloorRun,
  beginCycle,
  disableFloorRun,
  endCycleProgress,
  incrementFloorCycle,
  readFloorRunState,
  recordFloorSignal,
  setFloorRunPhase,
} from "./run-control";

function jsonResponse(body: unknown, ok = true) {
  return { ok, status: ok ? 200 : 500, json: async () => body };
}

describe("floor run-control (Supabase-backed)", () => {
  beforeEach(() => {
    process.env.NEXT_PUBLIC_SUPABASE_URL = "https://example.supabase.co";
    process.env.SUPABASE_SERVICE_ROLE_KEY = "service-role-test-key";
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    delete process.env.NEXT_PUBLIC_SUPABASE_URL;
    delete process.env.SUPABASE_SERVICE_ROLE_KEY;
  });

  it("readFloorRunState maps the row to FloorRunStatus", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse([{
      id: 1,
      enabled: true,
      in_progress: false,
      run_id: "run-1",
      cycle: 3,
      phase: "technical",
      last_message: "Cycle 3: technical desk analyzing gold...",
      last_signal: null,
      updated_at: "2026-07-18T00:00:00.000Z",
    }]));
    vi.stubGlobal("fetch", fetchMock);

    const status = await readFloorRunState();
    expect(status).toEqual({
      running: true,
      runId: "run-1",
      cycle: 3,
      phase: "technical",
      lastMessage: "Cycle 3: technical desk analyzing gold...",
      lastSignal: null,
    });
  });

  it("armFloorRun returns true and arms the row when not already enabled", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse([{ id: 1 }]));
    vi.stubGlobal("fetch", fetchMock);

    const armed = await armFloorRun("run-2");
    expect(armed).toBe(true);

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toContain("enabled=eq.false");
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(init.body)).toMatchObject({
      enabled: true,
      run_id: "run-2",
      cycle: 0,
      phase: "macro",
    });
  });

  it("armFloorRun returns false when already enabled", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse([]));
    vi.stubGlobal("fetch", fetchMock);

    expect(await armFloorRun("run-3")).toBe(false);
  });

  it("disableFloorRun PATCHes enabled=false", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse([{ id: 1 }]));
    vi.stubGlobal("fetch", fetchMock);

    await disableFloorRun();
    const [, init] = fetchMock.mock.calls[0];
    expect(JSON.parse(init.body)).toMatchObject({ enabled: false });
  });

  it("beginCycle returns true and marks in_progress when enabled and free", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse([{ id: 1 }]));
    vi.stubGlobal("fetch", fetchMock);

    const started = await beginCycle();
    expect(started).toBe(true);

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toContain("enabled=eq.true");
    expect(url).toContain("in_progress=eq.false");
    expect(JSON.parse(init.body)).toMatchObject({ in_progress: true });
  });

  it("beginCycle returns false when already in progress or disabled", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse([]));
    vi.stubGlobal("fetch", fetchMock);

    expect(await beginCycle()).toBe(false);
  });

  it("endCycleProgress PATCHes in_progress=false", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse([{ id: 1 }]));
    vi.stubGlobal("fetch", fetchMock);

    await endCycleProgress();
    const [, init] = fetchMock.mock.calls[0];
    expect(JSON.parse(init.body)).toMatchObject({ in_progress: false });
  });

  it("incrementFloorCycle reads current cycle then PATCHes cycle+1", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse([{ id: 1, cycle: 4 }]))
      .mockResolvedValueOnce(jsonResponse([{ id: 1 }]));
    vi.stubGlobal("fetch", fetchMock);

    const cycle = await incrementFloorCycle();
    expect(cycle).toBe(5);

    const [, patchInit] = fetchMock.mock.calls[1];
    expect(JSON.parse(patchInit.body)).toMatchObject({ cycle: 5 });
  });

  it("setFloorRunPhase PATCHes phase and lastMessage", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse([{ id: 1 }]));
    vi.stubGlobal("fetch", fetchMock);

    await setFloorRunPhase("pm", "Cycle 5: PM deciding signal or pass...");
    const [, init] = fetchMock.mock.calls[0];
    expect(JSON.parse(init.body)).toMatchObject({
      phase: "pm",
      last_message: "Cycle 5: PM deciding signal or pass...",
    });
  });

  it("recordFloorSignal PATCHes last_signal", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse([{ id: 1 }]));
    vi.stubGlobal("fetch", fetchMock);

    const signal = {
      direction: "long" as const,
      entry: 2400,
      stopLoss: 2390,
      takeProfit: 2420,
      confidence: 72,
      body: "Breakout setup.",
      createdAt: "2026-07-18T00:00:00.000Z",
    };
    await recordFloorSignal(signal);

    const [, init] = fetchMock.mock.calls[0];
    expect(JSON.parse(init.body)).toMatchObject({ last_signal: signal });
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd web && npx vitest run src/lib/floor/run-control.test.ts`
Expected: FAIL — `armFloorRun`, `beginCycle`, `disableFloorRun`,
`endCycleProgress`, `incrementFloorCycle`, `readFloorRunState`,
`recordFloorSignal`, `setFloorRunPhase` are not exported yet.

- [ ] **Step 3: Write the implementation**

Replace the entire contents of `web/src/lib/floor/run-control.ts`:

```ts
import type { FloorGoldSignal, FloorRunPhase, FloorRunStatus } from "./types";
import { floorSupabaseConfig, floorSupabaseHeaders } from "./supabase-config";

const TABLE = "floor_run_state";

type FloorRunStateRow = {
  id: number;
  enabled: boolean;
  in_progress: boolean;
  run_id: string | null;
  cycle: number;
  phase: FloorRunPhase;
  last_message: string;
  last_signal: FloorGoldSignal | null;
  updated_at: string;
};

type PatchFields = Partial<{
  enabled: boolean;
  in_progress: boolean;
  run_id: string | null;
  cycle: number;
  phase: FloorRunPhase;
  last_message: string;
  last_signal: FloorGoldSignal | null;
}>;

function requireConfig() {
  const cfg = floorSupabaseConfig();
  if (!cfg) throw new Error("Supabase service-role configuration is unavailable");
  return cfg;
}

async function readRow(): Promise<FloorRunStateRow> {
  const cfg = requireConfig();
  const response = await fetch(`${cfg.url}/rest/v1/${TABLE}?id=eq.1&select=*`, {
    headers: floorSupabaseHeaders(cfg.serviceKey),
  });
  if (!response.ok) {
    throw new Error(`Could not read floor run state (HTTP ${response.status})`);
  }
  const rows = await response.json() as FloorRunStateRow[];
  const row = rows[0];
  if (!row) {
    throw new Error("floor_run_state row is missing — has the migration been run?");
  }
  return row;
}

/** Plain PATCH — no WHERE-clause guard, for updates that don't need CAS. */
async function patchRow(patch: PatchFields): Promise<void> {
  const cfg = requireConfig();
  const response = await fetch(`${cfg.url}/rest/v1/${TABLE}?id=eq.1`, {
    method: "PATCH",
    headers: { ...floorSupabaseHeaders(cfg.serviceKey), Prefer: "return=minimal" },
    body: JSON.stringify({ ...patch, updated_at: new Date().toISOString() }),
  });
  if (!response.ok) {
    throw new Error(`Could not update floor run state (HTTP ${response.status})`);
  }
}

/**
 * Compare-and-swap PATCH: only applies if the row currently matches
 * `whereEq` (e.g. `{ enabled: false }`). Returns true iff a row was
 * actually updated — false means someone else's invocation already
 * changed the state first. This is what makes a manual "Run now" and a
 * cron tick landing at the same instant safe.
 */
async function patchRowIf(whereEq: Record<string, boolean>, patch: PatchFields): Promise<boolean> {
  const cfg = requireConfig();
  const whereQuery = Object.entries(whereEq)
    .map(([key, value]) => `${key}=eq.${value}`)
    .join("&");
  const response = await fetch(`${cfg.url}/rest/v1/${TABLE}?id=eq.1&${whereQuery}`, {
    method: "PATCH",
    headers: { ...floorSupabaseHeaders(cfg.serviceKey), Prefer: "return=representation" },
    body: JSON.stringify({ ...patch, updated_at: new Date().toISOString() }),
  });
  if (!response.ok) {
    throw new Error(`Could not update floor run state (HTTP ${response.status})`);
  }
  const rows = await response.json() as FloorRunStateRow[];
  return rows.length > 0;
}

function toStatus(row: FloorRunStateRow): FloorRunStatus {
  return {
    running: row.enabled,
    runId: row.run_id,
    cycle: row.cycle,
    phase: row.phase,
    lastMessage: row.last_message,
    lastSignal: row.last_signal,
  };
}

export async function readFloorRunState(): Promise<FloorRunStatus> {
  return toStatus(await readRow());
}

/** Arms the hunter; false if it was already enabled (mirrors the old
 * "already running" 409 check, now race-safe via the WHERE clause). */
export async function armFloorRun(runId: string): Promise<boolean> {
  return patchRowIf(
    { enabled: false },
    {
      enabled: true,
      in_progress: false,
      run_id: runId,
      cycle: 0,
      phase: "macro",
      last_message: "Gold hunter started.",
      last_signal: null,
    },
  );
}

export async function disableFloorRun(): Promise<void> {
  await patchRow({ enabled: false });
}

/** Claims the right to run one cycle; false if disabled or a cycle is
 * already in progress (concurrency guard for cron vs. manual triggers). */
export async function beginCycle(): Promise<boolean> {
  return patchRowIf({ enabled: true, in_progress: false }, { in_progress: true });
}

export async function endCycleProgress(): Promise<void> {
  await patchRow({ in_progress: false });
}

export async function incrementFloorCycle(): Promise<number> {
  const row = await readRow();
  const cycle = row.cycle + 1;
  await patchRow({ cycle });
  return cycle;
}

export async function setFloorRunPhase(phase: FloorRunPhase, message: string): Promise<void> {
  await patchRow({ phase, last_message: message });
}

export async function recordFloorSignal(signal: FloorGoldSignal): Promise<void> {
  await patchRow({ last_signal: signal });
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd web && npx vitest run src/lib/floor/run-control.test.ts`
Expected: PASS, all 10 tests green.

- [ ] **Step 5: Commit**

```bash
git add web/src/lib/floor/run-control.ts web/src/lib/floor/run-control.test.ts
git commit -m "Rewrite run-control.ts as Supabase-backed durable state"
```

---

### Task 5: Rewrite `gold-cycle.ts` — drop the loop, add `runOneGoldCycleIfEnabled`

**Files:**
- Modify: `web/src/lib/floor/gold-cycle.ts` (full rewrite)
- Test: Create `web/src/lib/floor/gold-cycle.test.ts`

Removes the internal `while` + 90s-sleep loop and all `appendFloorLog`/
`shouldStopFloorRun` calls (both gone from `run-control.ts` now). Per the
spec, mid-cycle cancellation on Stop is out of scope — a cycle that's
already running is left to finish; only *future* cycles are prevented.

- [ ] **Step 1: Write the failing test**

Create `web/src/lib/floor/gold-cycle.test.ts`:

```ts
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("./run-control", () => ({
  readFloorRunState: vi.fn(),
  beginCycle: vi.fn(),
  endCycleProgress: vi.fn(),
  incrementFloorCycle: vi.fn(),
  setFloorRunPhase: vi.fn(),
  recordFloorSignal: vi.fn(),
}));
vi.mock("./gold-context", () => ({
  loadGoldFloorContext: vi.fn(),
}));
vi.mock("./llm", () => ({
  floorChat: vi.fn(),
  parseDeskBrief: vi.fn(),
  parsePmDecision: vi.fn(),
}));
vi.mock("./prompts", () => ({ buildDeskMessages: vi.fn() }));
vi.mock("./telegram", () => ({ sendFloorGoldAlert: vi.fn() }));
vi.mock("./store", () => ({ insertFloorBrief: vi.fn() }));

import { runOneGoldCycleIfEnabled } from "./gold-cycle";
import { loadGoldFloorContext } from "./gold-context";
import * as runControl from "./run-control";

const IDLE_STATUS = {
  running: false, runId: null, cycle: 0, phase: "idle" as const,
  lastMessage: "", lastSignal: null,
};

describe("runOneGoldCycleIfEnabled", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("does nothing when the hunter is not enabled", async () => {
    vi.mocked(runControl.readFloorRunState).mockResolvedValue(IDLE_STATUS);

    await runOneGoldCycleIfEnabled();

    expect(runControl.beginCycle).not.toHaveBeenCalled();
    expect(loadGoldFloorContext).not.toHaveBeenCalled();
  });

  it("does nothing when a cycle is already in progress", async () => {
    vi.mocked(runControl.readFloorRunState).mockResolvedValue({
      ...IDLE_STATUS, running: true, runId: "run-1",
    });
    vi.mocked(runControl.beginCycle).mockResolvedValue(false);

    await runOneGoldCycleIfEnabled();

    expect(loadGoldFloorContext).not.toHaveBeenCalled();
  });

  it("always clears in_progress, even when the cycle throws", async () => {
    vi.mocked(runControl.readFloorRunState).mockResolvedValue({
      ...IDLE_STATUS, running: true, runId: "run-1",
    });
    vi.mocked(runControl.beginCycle).mockResolvedValue(true);
    vi.mocked(runControl.incrementFloorCycle).mockRejectedValue(new Error("boom"));

    await expect(runOneGoldCycleIfEnabled()).rejects.toThrow("boom");

    expect(runControl.endCycleProgress).toHaveBeenCalledTimes(1);
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd web && npx vitest run src/lib/floor/gold-cycle.test.ts`
Expected: FAIL — `runOneGoldCycleIfEnabled` is not exported yet (current
export is `runGoldFloorLoop`).

- [ ] **Step 3: Write the implementation**

Replace the entire contents of `web/src/lib/floor/gold-cycle.ts`:

```ts
import { floorChat, parseDeskBrief, parsePmDecision } from "./llm";
import { buildDeskMessages } from "./prompts";
import { sendFloorGoldAlert } from "./telegram";
import {
  beginCycle,
  endCycleProgress,
  incrementFloorCycle,
  readFloorRunState,
  recordFloorSignal,
  setFloorRunPhase,
} from "./run-control";
import { insertFloorBrief } from "./store";
import { loadGoldFloorContext } from "./gold-context";
import { FLOOR_DESKS, GOLD_SYMBOL, type FloorTone } from "./types";

function pmBody(decision: ReturnType<typeof parsePmDecision>): string {
  if (decision.action !== "signal" || !decision.direction) {
    return `PASS — ${decision.body}`;
  }
  return [
    `SIGNAL ${decision.direction.toUpperCase()} @ ${decision.entry}`,
    `SL ${decision.stopLoss} | TP ${decision.takeProfit}`,
    `Confidence ${decision.confidence ?? 0}%`,
    decision.body,
  ].join(" — ");
}

async function runOneGoldCycle(runId: string): Promise<void> {
  const cycle = await incrementFloorCycle();
  const context = await loadGoldFloorContext();
  const peerNotes: string[] = [];

  for (const desk of FLOOR_DESKS.filter((item) => item !== "pm")) {
    await setFloorRunPhase(desk, `Cycle ${cycle}: ${desk} desk analyzing gold...`);
    try {
      const brief = parseDeskBrief(
        await floorChat(buildDeskMessages(desk, context), { desk }),
      );
      await insertFloorBrief({ desk, ...brief, runId });
      peerNotes.push(`${desk} (${brief.tone}): ${brief.body}`);
    } catch {
      const fallback = `${desk} desk unavailable this cycle.`;
      await insertFloorBrief({ desk, tone: "neutral", body: fallback, runId });
    }
  }

  await setFloorRunPhase("pm", `Cycle ${cycle}: PM deciding signal or pass...`);
  let pmTone: FloorTone = "neutral";
  let pmText = "PM unavailable this cycle.";

  try {
    const decision = parsePmDecision(
      await floorChat(
        buildDeskMessages("pm", {
          ...context,
          peerBriefsBlock: peerNotes.join("\n") || "No peer notes.",
        }),
        { desk: "pm" },
      ),
    );
    pmTone = decision.tone;
    pmText = pmBody(decision);
    await insertFloorBrief({ desk: "pm", tone: pmTone, body: pmText, runId });

    if (
      decision.action === "signal"
      && decision.direction
      && decision.entry
      && decision.stopLoss
      && decision.takeProfit
    ) {
      const signal = {
        direction: decision.direction,
        entry: decision.entry,
        stopLoss: decision.stopLoss,
        takeProfit: decision.takeProfit,
        confidence: decision.confidence ?? 0,
        body: decision.body,
        createdAt: new Date().toISOString(),
      };
      await recordFloorSignal(signal);
      const alerted = await sendFloorGoldAlert({
        symbol: GOLD_SYMBOL,
        ...signal,
        rationale: decision.body,
      });
      const alertMsg = alerted
        ? `Cycle ${cycle}: SIGNAL dropped — Telegram sent.`
        : `Cycle ${cycle}: SIGNAL dropped — saved on floor.`;
      await setFloorRunPhase("pm", alertMsg);
      return;
    }

    await setFloorRunPhase("pm", `Cycle ${cycle}: PASS — no signal this round.`);
  } catch {
    const fallback = "PM desk unavailable this cycle.";
    await insertFloorBrief({ desk: "pm", tone: "neutral", body: fallback, runId });
    await setFloorRunPhase("pm", `Cycle ${cycle}: PM error — pass by default.`);
  }
}

/**
 * Runs exactly one gold-hunt cycle if the hunter is enabled and no other
 * invocation (manual or cron) currently has one in progress. Called
 * identically from the Run button (immediate, awaited) and the cron
 * endpoint (on its external schedule) — this is the only place either
 * trigger touches cycle logic.
 */
export async function runOneGoldCycleIfEnabled(): Promise<void> {
  const state = await readFloorRunState();
  if (!state.running || !state.runId) return;

  const started = await beginCycle();
  if (!started) return;

  try {
    await runOneGoldCycle(state.runId);
  } finally {
    await endCycleProgress();
  }
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd web && npx vitest run src/lib/floor/gold-cycle.test.ts`
Expected: PASS, all 3 tests green.

- [ ] **Step 5: Commit**

```bash
git add web/src/lib/floor/gold-cycle.ts web/src/lib/floor/gold-cycle.test.ts
git commit -m "Replace floor's internal loop with one-cycle-per-invocation model"
```

---

### Task 6: Update the four API routes

**Files:**
- Modify: `web/src/app/api/admin/floor/run/route.ts`
- Modify: `web/src/app/api/admin/floor/stop/route.ts`
- Modify: `web/src/app/api/cron/floor/route.ts`
- Modify: `web/src/app/api/floor/board/route.ts`

The old `DELETE` handler on `/api/admin/floor/run` is removed as dead code
— the client only ever calls the dedicated `/api/admin/floor/stop` POST
endpoint (verified: `FloorRunControls.tsx`'s `stopRun()` calls
`/api/admin/floor/stop`, never `DELETE /api/admin/floor/run`).

- [ ] **Step 1: Rewrite `web/src/app/api/admin/floor/run/route.ts`**

```ts
import { randomUUID } from "crypto";

import { NextResponse } from "next/server";

import { requireAdminApi } from "@/lib/admin-api-guard";
import { runOneGoldCycleIfEnabled } from "@/lib/floor/gold-cycle";
import { armFloorRun, readFloorRunState } from "@/lib/floor/run-control";

export const dynamic = "force-dynamic";
export const maxDuration = 300;

export async function GET() {
  const denied = await requireAdminApi();
  if (denied) return denied;

  return NextResponse.json(await readFloorRunState());
}

export async function POST() {
  const denied = await requireAdminApi();
  if (denied) return denied;

  const runId = randomUUID();
  const armed = await armFloorRun(runId);
  if (!armed) {
    return NextResponse.json(
      { error: "Gold hunter is already running." },
      { status: 409 },
    );
  }

  try {
    await runOneGoldCycleIfEnabled();
  } catch {
    // The run is armed regardless — the next cron tick retries this cycle.
  }

  return NextResponse.json({
    ok: true,
    started: true,
    runId,
    message: "Gold hunter started. It will run until you press Stop.",
  });
}
```

- [ ] **Step 2: Rewrite `web/src/app/api/admin/floor/stop/route.ts`**

```ts
import { NextResponse } from "next/server";

import { requireAdminApi } from "@/lib/admin-api-guard";
import { disableFloorRun, readFloorRunState } from "@/lib/floor/run-control";

export const dynamic = "force-dynamic";

export async function POST() {
  const denied = await requireAdminApi();
  if (denied) return denied;

  await disableFloorRun();
  return NextResponse.json({
    ok: true,
    ...(await readFloorRunState()),
    message: "Stop requested. No further cycles will start.",
  });
}
```

- [ ] **Step 3: Rewrite `web/src/app/api/cron/floor/route.ts`**

```ts
import { NextResponse } from "next/server";

import { floorCronAuthorized } from "@/lib/floor/auth";
import { runOneGoldCycleIfEnabled } from "@/lib/floor/gold-cycle";

export const dynamic = "force-dynamic";
export const maxDuration = 300;

async function handle(request: Request) {
  const secret = process.env.FLOOR_CRON_SECRET?.trim() ?? "";
  if (!secret) {
    return NextResponse.json(
      { error: "FLOOR_CRON_SECRET must be set for the trading floor cron" },
      { status: 500 },
    );
  }
  if (!floorCronAuthorized(request, secret)) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  try {
    await runOneGoldCycleIfEnabled();
    return NextResponse.json({ ok: true });
  } catch (error) {
    const message = error instanceof Error ? error.message : "floor cycle failed";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}

export async function GET(request: Request) {
  return handle(request);
}

export async function POST(request: Request) {
  return handle(request);
}
```

- [ ] **Step 4: Rewrite `web/src/app/api/floor/board/route.ts`**

```ts
import { NextResponse } from "next/server";

import { readFloorRunState } from "@/lib/floor/run-control";
import { GOLD_SYMBOL, type FloorRunStatus } from "@/lib/floor/types";
import { isAdminEmail } from "@/lib/supabase/admin";
import { createClient } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

type FloorBriefRow = {
  desk: string;
  tone: string;
  body: string;
  created_at: string;
};

function scanLineFromSnapshot(snapshot: FloorRunStatus): string {
  if (snapshot.running) {
    return snapshot.lastMessage || `Cycle ${snapshot.cycle} — ${snapshot.phase}`;
  }
  if (snapshot.lastSignal) {
    return `Last signal: ${snapshot.lastSignal.direction.toUpperCase()} @ ${snapshot.lastSignal.entry}`;
  }
  return "Press Run to start the gold AI hunter.";
}

export async function GET() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  if (!isAdminEmail(user.email)) {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }

  const { data, error } = await supabase
    .from("floor_briefs")
    .select("desk, tone, body, created_at")
    .order("created_at", { ascending: false })
    .limit(60);

  if (error) {
    const missing =
      error.code === "PGRST205" ||
      /floor_briefs|schema cache|does not exist/i.test(error.message ?? "");
    return NextResponse.json(
      {
        error: missing
          ? "Floor tables are missing. Run supabase/migrations/20260715_trading_floor.sql in the Supabase SQL editor."
          : "Could not load gold floor board",
        detail: error.message,
      },
      { status: 500 },
    );
  }

  const log = (data ?? [] as FloorBriefRow[]).map((row) => ({
    ts: row.created_at,
    desk: row.desk,
    tone: row.tone,
    text: row.body,
  }));

  const snapshot = await readFloorRunState();

  return NextResponse.json({
    symbol: GOLD_SYMBOL,
    log,
    lastSignal: snapshot.lastSignal,
    scanLine: scanLineFromSnapshot(snapshot),
  });
}
```

- [ ] **Step 5: Typecheck**

Run: `cd web && npx tsc --noEmit`
Expected: no errors referencing these four route files.

- [ ] **Step 6: Commit**

```bash
git add web/src/app/api/admin/floor/run/route.ts \
        web/src/app/api/admin/floor/stop/route.ts \
        web/src/app/api/cron/floor/route.ts \
        web/src/app/api/floor/board/route.ts
git commit -m "Wire floor API routes to durable run state and single-cycle execution"
```

---

### Task 7: Update admin UI components

**Files:**
- Modify: `web/src/components/floor/FloorRunControls.tsx:8-16`
- Modify: `web/src/components/floor/TradingFloor.tsx:19-27,67-69`

- [ ] **Step 1: Remove `log` from `FloorRunControls.tsx`'s `IDLE_STATUS`**

In `web/src/components/floor/FloorRunControls.tsx`, change:

```ts
const IDLE_STATUS: FloorRunStatus = {
  running: false,
  runId: null,
  cycle: 0,
  phase: "idle",
  lastMessage: "",
  lastSignal: null,
  log: [],
};
```

to:

```ts
const IDLE_STATUS: FloorRunStatus = {
  running: false,
  runId: null,
  cycle: 0,
  phase: "idle",
  lastMessage: "",
  lastSignal: null,
};
```

- [ ] **Step 2: Update `TradingFloor.tsx`**

In `web/src/components/floor/TradingFloor.tsx`, change the `IDLE_STATUS`
constant the same way (remove the `log: []` line), and change:

```ts
const log = runStatus.running && runStatus.log.length > 0
  ? runStatus.log
  : boardLog;
```

to:

```ts
const log = boardLog;
```

- [ ] **Step 3: Typecheck**

Run: `cd web && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 4: Run the full web test suite**

Run: `cd web && npm test`
Expected: all tests pass except the pre-existing, unrelated
`scrollIntoView is not a function` failure in `GoldFloorBoard`/
`TradingFloor.test.tsx` (out of scope, flagged separately).

- [ ] **Step 5: Commit**

```bash
git add web/src/components/floor/FloorRunControls.tsx \
        web/src/components/floor/TradingFloor.tsx
git commit -m "Admin floor UI reads log from floor_briefs instead of run status"
```

---

### Task 8: GitHub Actions backup cron

**Files:**
- Create: `.github/workflows/floor.yml`

Mirrors `engine.yml`'s dual-trigger philosophy: an external cron service is
the primary driver (~2 min, configured outside this repo), this workflow
is the best-effort backup. Unlike `engine.yml`, there's no Python/Node
compute to run in the Actions runner — this is a plain HTTP call to the
already-deployed Vercel route.

- [ ] **Step 1: Write the workflow**

```yaml
name: Trading floor cron (backup)

on:
  schedule:
    # Backup only — GitHub's schedule is best-effort and can drift.
    # Primary trigger: an external cron service hits /api/cron/floor
    # every ~2 minutes. This runs every 5 minutes as a safety net.
    - cron: "*/5 * * * *"
  workflow_dispatch: {}

concurrency:
  group: floor-cron
  cancel-in-progress: false

jobs:
  tick:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - name: Run one floor cycle if enabled
        run: |
          curl -sf -X POST "https://${{ vars.FLOOR_DOMAIN }}/api/cron/floor" \
            -H "Authorization: Bearer ${{ secrets.FLOOR_CRON_SECRET }}"
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/floor.yml
git commit -m "Add GitHub Actions backup cron for the trading floor"
```

---

### Task 9: Operational rollout checklist + full verification

**Files:** None (verification + manual setup steps only)

- [ ] **Step 1: Full test suite**

Run: `cd web && npm test`
Expected: all tests pass except the pre-existing `scrollIntoView` failure.

- [ ] **Step 2: Lint + build**

Run: `cd web && npm run lint && npm run build`
Expected: no errors.

- [ ] **Step 3: Manual operational steps (not code — do these before relying on the feature in production)**

1. Confirm the Task 1 migration has been applied to the production
   Supabase project (not just local/dev).
2. Set `FLOOR_CRON_SECRET` in Vercel's project env vars (Production +
   Preview) to a strong random value.
3. Set the `FLOOR_DOMAIN` repository variable in GitHub (Settings →
   Secrets and variables → Actions → Variables) to the production domain
   (e.g. `web-seven-pi-76.vercel.app`, no `https://` prefix), and
   `FLOOR_CRON_SECRET` as a matching repository *secret*.
4. Register an external cron service (e.g. cron-job.org, matching the
   Python engine's setup) to hit `POST https://<domain>/api/cron/floor`
   every ~2 minutes with header `Authorization: Bearer <FLOOR_CRON_SECRET>`.
5. Smoke test: click Run in the admin UI, confirm a cycle completes and
   `floor_run_state.enabled=true`; wait for a cron tick and confirm
   `cycle` increments without touching the admin page. Click Stop and
   confirm no further cycles start.

- [ ] **Step 4: Final commit (if any cleanup was needed)**

```bash
git status
```

If clean, nothing further to commit — this task is verification only.
