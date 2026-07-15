# Trading Floor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a member dashboard Trading Floor tab with a 4-desk ambient board plus PM chat, powered by a separate floor LLM API, without changing the signals confirm/detect/RAG/Telegram path.

**Architecture:** Floor lives entirely in the Next.js app. A secret-protected cron route gathers read-only context (session clock text, calendar summary, headlines, open/recent signals), calls the floor LLM once per desk, and inserts `floor_briefs` under one `run_id`. Chat loads the latest board pack, calls the PM once, and stores messages per user. SEA-LION confirm code is never imported.

**Tech Stack:** Next.js App Router / TypeScript, Supabase (schema + RLS), OpenAI-compatible floor LLM HTTP API, vitest.

**Spec:** `docs/superpowers/specs/2026-07-15-trading-floor-design.md`  
**Branch:** `feature/trading-floor`

**Hard rule:** Do not modify `signals/composer.py`, `signals/run.py` confirm path, detectors, RAG, or Telegram clients.

---

## File map

| File | Responsibility |
|------|----------------|
| `supabase/schema.sql` | Append `floor_briefs` + `floor_chat_messages` + RLS/policies |
| `web/src/lib/floor/types.ts` | Desk/tone/brief/message types |
| `web/src/lib/floor/llm.ts` | Floor OpenAI-compatible chat client (`FLOOR_LLM_*`) |
| `web/src/lib/floor/prompts.ts` | Desk + PM system/user prompt builders |
| `web/src/lib/floor/context.ts` | Read-only context pack for board runs |
| `web/src/lib/floor/board.ts` | Load latest briefs; run one board cycle (service role) |
| `web/src/lib/floor/chat.ts` | Load/send chat; rate limit; PM call |
| `web/src/lib/floor/auth.ts` | Cron secret check (Bearer or `?secret=`) |
| `web/src/app/api/cron/floor/route.ts` | Cron entrypoint |
| `web/src/app/api/floor/board/route.ts` | Member GET board |
| `web/src/app/api/floor/chat/route.ts` | Member GET/POST chat |
| `web/src/components/floor/DeskBoard.tsx` | Four desk cards |
| `web/src/components/floor/FloorChat.tsx` | Client chat UI |
| `web/src/components/floor/TradingFloor.tsx` | Board + chat composition |
| `web/src/app/dashboard/page.tsx` | Add `floor` tab only (signals tabs unchanged) |
| `.env.example` | Document `FLOOR_LLM_*` + `FLOOR_CRON_SECRET` |
| `web/src/lib/floor/*.test.ts` | Unit tests for parse, prompts, rate limit, auth |

---

### Task 1: Schema — floor tables

**Files:**
- Modify: `supabase/schema.sql` (append only; do not alter `signals` / `ai_events`)

- [ ] **Step 1: Append floor schema at end of `supabase/schema.sql`**

```sql
-- Trading Floor (independent of signals confirm engine)
create table if not exists public.floor_briefs (
    id uuid primary key default gen_random_uuid(),
    desk text not null check (desk in ('macro', 'technical', 'news', 'pm')),
    tone text not null check (tone in ('bullish', 'neutral', 'cautious')),
    body text not null,
    run_id text not null,
    created_at timestamptz not null default now()
);

create index if not exists floor_briefs_desk_created_at_idx
    on public.floor_briefs (desk, created_at desc);

create index if not exists floor_briefs_run_id_idx
    on public.floor_briefs (run_id);

alter table public.floor_briefs enable row level security;

drop policy if exists "members read floor briefs" on public.floor_briefs;
create policy "members read floor briefs"
    on public.floor_briefs for select
    to authenticated
    using (true);

create table if not exists public.floor_chat_messages (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users (id) on delete cascade,
    role text not null check (role in ('user', 'assistant')),
    content text not null,
    created_at timestamptz not null default now()
);

create index if not exists floor_chat_messages_user_created_at_idx
    on public.floor_chat_messages (user_id, created_at desc);

alter table public.floor_chat_messages enable row level security;

drop policy if exists "members read own floor chat" on public.floor_chat_messages;
create policy "members read own floor chat"
    on public.floor_chat_messages for select
    to authenticated
    using (auth.uid() = user_id);

drop policy if exists "members insert own floor chat" on public.floor_chat_messages;
create policy "members insert own floor chat"
    on public.floor_chat_messages for insert
    to authenticated
    with check (auth.uid() = user_id);
```

Note: service-role inserts bypass RLS (cron writes briefs; chat inserts use the member session).

- [ ] **Step 2: Commit**

```bash
git add supabase/schema.sql
git commit -m "Add floor_briefs and floor_chat_messages schema."
```

---

### Task 2: Floor types + LLM client

**Files:**
- Create: `web/src/lib/floor/types.ts`
- Create: `web/src/lib/floor/llm.ts`
- Create: `web/src/lib/floor/llm.test.ts`

- [ ] **Step 1: Write failing tests for JSON brief parse**

`web/src/lib/floor/llm.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { parseDeskBrief } from "./llm";

describe("parseDeskBrief", () => {
  it("parses tone and body", () => {
    const out = parseDeskBrief(
      '{"tone":"cautious","body":"London open with USD high-impact ahead."}',
    );
    expect(out).toEqual({
      tone: "cautious",
      body: "London open with USD high-impact ahead.",
    });
  });

  it("rejects invalid tone to neutral with truncated body fallback", () => {
    const out = parseDeskBrief('{"tone":"yolo","body":"ok"}');
    expect(out.tone).toBe("neutral");
    expect(out.body).toBe("ok");
  });

  it("fail-closes on garbage", () => {
    const out = parseDeskBrief("not json");
    expect(out.tone).toBe("neutral");
    expect(out.body.length).toBeGreaterThan(0);
  });
});
```

- [ ] **Step 2: Run test — expect FAIL (module missing)**

```bash
cd web && npx vitest run src/lib/floor/llm.test.ts
```

Expected: fail to resolve `./llm` or `parseDeskBrief`.

- [ ] **Step 3: Implement types + client**

`web/src/lib/floor/types.ts`:

```ts
export const FLOOR_DESKS = ["macro", "technical", "news", "pm"] as const;
export type FloorDesk = (typeof FLOOR_DESKS)[number];

export const FLOOR_TONES = ["bullish", "neutral", "cautious"] as const;
export type FloorTone = (typeof FLOOR_TONES)[number];

export type FloorBrief = {
  id: string;
  desk: FloorDesk;
  tone: FloorTone;
  body: string;
  runId: string;
  createdAt: string;
};

export type FloorChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  createdAt: string;
};

export type DeskBriefResult = { tone: FloorTone; body: string };
```

`web/src/lib/floor/llm.ts`:

```ts
import type { DeskBriefResult, FloorTone } from "./types";
import { FLOOR_TONES } from "./types";

const MAX_BODY = 600;

export function parseDeskBrief(text: string): DeskBriefResult {
  const start = text.indexOf("{");
  const end = text.lastIndexOf("}");
  if (start === -1 || end <= start) {
    return { tone: "neutral", body: "Desk unavailable (unparseable reply)." };
  }
  try {
    const data = JSON.parse(text.slice(start, end + 1)) as {
      tone?: string;
      body?: string;
    };
    const tone = (FLOOR_TONES as readonly string[]).includes(data.tone ?? "")
      ? (data.tone as FloorTone)
      : "neutral";
    const body = String(data.body ?? "").trim().slice(0, MAX_BODY)
      || "Desk returned an empty brief.";
    return { tone, body };
  } catch {
    return { tone: "neutral", body: "Desk unavailable (invalid JSON)." };
  }
}

export async function floorChat(
  messages: { role: "system" | "user" | "assistant"; content: string }[],
  opts?: { temperature?: number },
): Promise<string> {
  const apiKey = process.env.FLOOR_LLM_API_KEY?.trim();
  const baseUrl = (process.env.FLOOR_LLM_BASE_URL || "https://api.openai.com/v1").replace(/\/$/, "");
  const model = process.env.FLOOR_LLM_MODEL?.trim();
  if (!apiKey || !model) {
    throw new Error("FLOOR_LLM_API_KEY and FLOOR_LLM_MODEL must be set");
  }
  const res = await fetch(`${baseUrl}/chat/completions`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model,
      temperature: opts?.temperature ?? 0.3,
      messages,
      response_format: { type: "json_object" },
    }),
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(`Floor LLM HTTP ${res.status}: ${detail.slice(0, 200)}`);
  }
  const json = (await res.json()) as {
    choices?: { message?: { content?: string } }[];
  };
  return json.choices?.[0]?.message?.content ?? "";
}
```

- [ ] **Step 4: Re-run tests — expect PASS**

```bash
cd web && npx vitest run src/lib/floor/llm.test.ts
```

- [ ] **Step 5: Commit**

```bash
git add web/src/lib/floor/types.ts web/src/lib/floor/llm.ts web/src/lib/floor/llm.test.ts
git commit -m "Add floor LLM client and desk brief parser."
```

---

### Task 3: Prompts + board context

**Files:**
- Create: `web/src/lib/floor/prompts.ts`
- Create: `web/src/lib/floor/prompts.test.ts`
- Create: `web/src/lib/floor/context.ts`

- [ ] **Step 1: Failing test — desk prompt includes role + context**

```ts
import { describe, expect, it } from "vitest";
import { buildDeskMessages, buildPmChatMessages } from "./prompts";

describe("floor prompts", () => {
  it("builds macro desk messages with calendar block", () => {
    const msgs = buildDeskMessages("macro", {
      sessionLine: "Market session: London",
      calendarBlock: "- USD CPI High",
      headlinesBlock: "- Cable soft",
      signalsBlock: "No open signals",
      peerBriefsBlock: "",
    });
    expect(msgs[0].role).toBe("system");
    expect(msgs[1].content).toContain("macro");
    expect(msgs[1].content).toContain("USD CPI");
  });

  it("PM chat includes board pack", () => {
    const msgs = buildPmChatMessages({
      question: "Is GBP risk-on right now?",
      boardPack: "macro: cautious — ...\nnews: neutral — ...",
      signalsBlock: "Open: none",
    });
    expect(msgs[1].content).toContain("GBP");
    expect(msgs[1].content).toContain("board");
  });
});
```

- [ ] **Step 2: Run — expect FAIL**

```bash
cd web && npx vitest run src/lib/floor/prompts.test.ts
```

- [ ] **Step 3: Implement prompts**

`web/src/lib/floor/prompts.ts`:

```ts
import type { FloorDesk } from "./types";

export type FloorContextBlocks = {
  sessionLine: string;
  calendarBlock: string;
  headlinesBlock: string;
  signalsBlock: string;
  peerBriefsBlock: string;
};

const DESK_JOB: Record<FloorDesk, string> = {
  macro:
    "You are the Macro/Session desk. Focus on FX session fit and calendar risk. Do not invent entries.",
  technical:
    "You are the Technical desk. Summarize bias from provided open/recent signal levels only. Do not invent candles or new setups.",
  news:
    "You are the News desk. Summarize catalysts from headlines vs symbols. Flag conflicts, do not invent news.",
  pm:
    "You are the PM/Risk desk. Synthesize peer desk notes into agreement, conflict, and size caution. Do not place trades.",
};

export function buildDeskMessages(
  desk: FloorDesk,
  ctx: FloorContextBlocks,
): { role: "system" | "user"; content: string }[] {
  const system =
    `${DESK_JOB[desk]}\n` +
    "Respond with ONLY JSON: " +
    '{"tone":"bullish"|"neutral"|"cautious","body":"<one short paragraph max 500 chars>"}';

  const user =
    `Desk assignment: ${desk}\n\n` +
    `${ctx.sessionLine}\n\n` +
    `Economic calendar:\n${ctx.calendarBlock}\n\n` +
    `Headlines:\n${ctx.headlinesBlock}\n\n` +
    `Signals book (read-only):\n${ctx.signalsBlock}\n` +
    (ctx.peerBriefsBlock
      ? `\nPeer desk notes:\n${ctx.peerBriefsBlock}\n`
      : "");

  return [
    { role: "system", content: system },
    { role: "user", content: user },
  ];
}

export function buildPmChatMessages(input: {
  question: string;
  boardPack: string;
  signalsBlock: string;
}): { role: "system" | "user"; content: string }[] {
  return [
    {
      role: "system",
      content:
        "You are the Trading Floor PM. Answer the member using the current desk board and open-book snapshot. " +
        "Be concise. Do not claim to execute trades. Respond with ONLY JSON: " +
        '{"tone":"bullish"|"neutral"|"cautious","body":"<answer>"}',
    },
    {
      role: "user",
      content:
        `Question: ${input.question}\n\n` +
        `Current board:\n${input.boardPack}\n\n` +
        `Signals book:\n${input.signalsBlock}`,
    },
  ];
}
```

- [ ] **Step 4: Implement context helper (service-role reads)**

`web/src/lib/floor/context.ts` — build plain-text blocks:

```ts
import type { FloorContextBlocks } from "./prompts";

export type SignalSnapshot = {
  symbol: string;
  timeframe: string;
  direction: string;
  status: string;
  entry: number;
  stopLoss: number;
  takeProfit: number;
};

export function formatSignalsBlock(rows: SignalSnapshot[]): string {
  if (!rows.length) return "No open or recent closed signals.";
  return rows
    .slice(0, 20)
    .map(
      (r) =>
        `- ${r.symbol} ${r.timeframe} ${r.direction} status=${r.status} ` +
        `entry=${r.entry} sl=${r.stopLoss} tp1=${r.takeProfit}`,
    )
    .join("\n");
}

export function emptyContext(): FloorContextBlocks {
  return {
    sessionLine: "Market session: unavailable",
    calendarBlock: "Calendar unavailable.",
    headlinesBlock: "No headlines.",
    signalsBlock: "No open or recent closed signals.",
    peerBriefsBlock: "",
  };
}

/** Soft-fill context: callers pass whatever they could fetch. */
export function buildContextBlocks(partial: Partial<FloorContextBlocks>): FloorContextBlocks {
  return { ...emptyContext(), ...partial };
}
```

For the board cron runner (Task 4), fetch:
- Session line: hardcode UTC buckets in `web/src/lib/floor/session.ts` mirroring `signals/session_clock.py` windows (copy the Asia/London/NY ranges; do not import Python).
- Calendar: optional Fair Economy JSON fetch in `web/src/lib/floor/calendar.ts` (soft-fail string).
- Headlines: optional RSS title fetch in `web/src/lib/floor/news.ts` (soft-fail; keep simple — concatenate a few feed titles, truncate).
- Signals: Supabase service-role `select` from `signals` where `status` in open/live or `created_at` last 48h, limit 20.

Keep each helper soft-failing to a short string — never throw out of the board cycle.

- [ ] **Step 5: Pass prompt tests; commit**

```bash
cd web && npx vitest run src/lib/floor/prompts.test.ts
git add web/src/lib/floor/
git commit -m "Add floor desk prompts and context formatters."
```

---

### Task 4: Board cycle + cron auth

**Files:**
- Create: `web/src/lib/floor/auth.ts`
- Create: `web/src/lib/floor/auth.test.ts`
- Create: `web/src/lib/floor/board.ts`
- Create: `web/src/app/api/cron/floor/route.ts`

- [ ] **Step 1: Auth tests**

```ts
import { describe, expect, it } from "vitest";
import { floorCronAuthorized } from "./auth";

describe("floorCronAuthorized", () => {
  it("accepts Bearer secret", () => {
    const req = new Request("https://x/api/cron/floor", {
      headers: { authorization: "Bearer s3cret" },
    });
    expect(floorCronAuthorized(req, "s3cret")).toBe(true);
  });

  it("accepts query secret", () => {
    const req = new Request("https://x/api/cron/floor?secret=s3cret");
    expect(floorCronAuthorized(req, "s3cret")).toBe(true);
  });

  it("rejects empty configured secret", () => {
    const req = new Request("https://x/api/cron/floor?secret=s3cret");
    expect(floorCronAuthorized(req, "")).toBe(false);
  });
});
```

- [ ] **Step 2: Implement auth + board runner**

`web/src/lib/floor/auth.ts`:

```ts
export function floorCronAuthorized(request: Request, secret: string): boolean {
  const trimmed = secret.trim();
  if (!trimmed) return false;
  const header = request.headers.get("authorization");
  if (header === `Bearer ${trimmed}`) return true;
  const querySecret = new URL(request.url).searchParams.get("secret");
  return querySecret === trimmed;
}
```

`web/src/lib/floor/board.ts` — core API:

```ts
import { randomUUID } from "crypto";
import { FLOOR_DESKS, type FloorBrief, type FloorDesk } from "./types";
import { floorChat, parseDeskBrief } from "./llm";
import { buildDeskMessages, type FloorContextBlocks } from "./prompts";

export async function latestBriefsByDesk(
  fetchLatest: (desk: FloorDesk) => Promise<FloorBrief | null>,
): Promise<Partial<Record<FloorDesk, FloorBrief>>> {
  const out: Partial<Record<FloorDesk, FloorBrief>> = {};
  for (const desk of FLOOR_DESKS) {
    const row = await fetchLatest(desk);
    if (row) out[desk] = row;
  }
  return out;
}

export async function runFloorBoardCycle(deps: {
  loadContext: () => Promise<FloorContextBlocks>;
  insertBrief: (row: {
    desk: FloorDesk;
    tone: string;
    body: string;
    runId: string;
  }) => Promise<void>;
  chat?: typeof floorChat;
}): Promise<{ runId: string; saved: FloorDesk[]; failed: FloorDesk[] }> {
  const chat = deps.chat ?? floorChat;
  const runId = randomUUID();
  const base = await deps.loadContext();
  const saved: FloorDesk[] = [];
  const failed: FloorDesk[] = [];
  const peerNotes: string[] = [];

  // macro, technical, news first; pm last with peer notes
  const early = FLOOR_DESKS.filter((d) => d !== "pm");
  for (const desk of early) {
    try {
      const reply = await chat(buildDeskMessages(desk, base));
      const brief = parseDeskBrief(reply);
      await deps.insertBrief({ desk, tone: brief.tone, body: brief.body, runId });
      peerNotes.push(`${desk} (${brief.tone}): ${brief.body}`);
      saved.push(desk);
    } catch {
      failed.push(desk);
    }
  }

  try {
    const pmCtx = {
      ...base,
      peerBriefsBlock: peerNotes.join("\n") || "No peer notes this run.",
    };
    const reply = await chat(buildDeskMessages("pm", pmCtx));
    const brief = parseDeskBrief(reply);
    await deps.insertBrief({
      desk: "pm",
      tone: brief.tone,
      body: brief.body,
      runId,
    });
    saved.push("pm");
  } catch {
    failed.push("pm");
  }

  return { runId, saved, failed };
}
```

Wire Supabase service-role insert in the cron route (or a small `web/src/lib/floor/store.ts`) using `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` — same pattern as `web/src/lib/supabase/admin.ts` REST fetches. Prefer appending helpers in `store.ts` rather than bloating `admin.ts`.

- [ ] **Step 3: Cron route**

`web/src/app/api/cron/floor/route.ts`:

```ts
import { NextResponse } from "next/server";
import { floorCronAuthorized } from "@/lib/floor/auth";
import { runFloorBoardCycle } from "@/lib/floor/board";
// import loadContext + insertBrief wiring from store/context modules

export const dynamic = "force-dynamic";
export const maxDuration = 60;

async function handle(request: Request) {
  const secret = process.env.FLOOR_CRON_SECRET || process.env.ENGINE_CRON_SECRET || "";
  if (!floorCronAuthorized(request, secret)) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  try {
    const result = await runFloorBoardCycle({
      loadContext: /* wired */,
      insertBrief: /* wired */,
    });
    return NextResponse.json({ ok: true, ...result });
  } catch (err) {
    const message = err instanceof Error ? err.message : "floor failed";
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

Prefer `FLOOR_CRON_SECRET`; fall back to `ENGINE_CRON_SECRET` only for ops convenience (document in `.env.example`).

- [ ] **Step 4: Unit-test board cycle with fake chat (no network)**

Add `web/src/lib/floor/board.test.ts` that injects `chat` returning fixed JSON and asserts `pm` runs after peers and soft-fails one desk.

- [ ] **Step 5: Commit**

```bash
git add web/src/lib/floor web/src/app/api/cron/floor
git commit -m "Add floor board cycle and cron route."
```

---

### Task 5: Member board + chat APIs

**Files:**
- Create: `web/src/lib/floor/chat.ts`
- Create: `web/src/lib/floor/chat.test.ts`
- Create: `web/src/app/api/floor/board/route.ts`
- Create: `web/src/app/api/floor/chat/route.ts`

- [ ] **Step 1: Rate-limit test**

```ts
import { describe, expect, it } from "vitest";
import { allowFloorChat } from "./chat";

describe("allowFloorChat", () => {
  it("allows first messages then blocks within window", () => {
    const now = 1_000_000;
    const timestamps: number[] = [];
    for (let i = 0; i < 6; i++) {
      expect(allowFloorChat(timestamps, now + i * 1000, 6, 60_000)).toBe(true);
      timestamps.push(now + i * 1000);
    }
    expect(allowFloorChat(timestamps, now + 7_000, 6, 60_000)).toBe(false);
  });
});
```

Implement in-memory Map keyed by `userId` in `chat.ts` (fine for single Vercel instance v1; document that multi-instance needs Redis later).

- [ ] **Step 2: `GET /api/floor/board`**

- Require `createClient()` session user; 401 if missing.
- Query latest brief per desk via member Supabase client (RLS allows select).
- Return `{ desks: FloorBrief[] }` sorted macro → technical → news → pm.

- [ ] **Step 3: `GET/POST /api/floor/chat`**

- GET: last 50 messages for `auth.uid()`, ascending for UI.
- POST body: `{ message: string }` (trim, max 1000 chars).
- Rate-limit; insert user row; build board pack from latest briefs; call PM via `floorChat` + `parseDeskBrief`; insert assistant row with `body`; return both messages.
- Soft-fail LLM: insert assistant “Floor PM unavailable…” with tone neutral; still 200.

- [ ] **Step 4: Commit**

```bash
git add web/src/lib/floor web/src/app/api/floor
git commit -m "Add member floor board and chat API routes."
```

---

### Task 6: Dashboard UI — Trading Floor tab

**Files:**
- Create: `web/src/components/floor/DeskBoard.tsx`
- Create: `web/src/components/floor/FloorChat.tsx`
- Create: `web/src/components/floor/TradingFloor.tsx`
- Modify: `web/src/app/dashboard/page.tsx` (tab plumbing only)

- [ ] **Step 1: `DeskBoard`** — four cards; empty → “Desks warming up”; show tone chip + body + relative time.

- [ ] **Step 2: `FloorChat`** — client component: load history on mount, form submit → POST, append messages. Use existing paper/ink/slate tokens; no emoji in UI copy.

- [ ] **Step 3: `TradingFloor`** — server or client wrapper: fetch board (server preferred) + render `DeskBoard` then `FloorChat`.

- [ ] **Step 4: Dashboard tab**

In `web/src/app/dashboard/page.tsx`:
1. Extend `currentTab` parser to accept `"floor"`.
2. Add nav `Link` to `/dashboard?tab=floor`.
3. When `currentTab === "floor"`, render `<TradingFloor />` instead of `SessionSection`.
4. Leave All / Super scalp / Scalping / Swing paths unchanged.
5. When floor is active, set shell title/subtitle to Trading Floor copy (optional prop on `DashboardShell` or local heading).

- [ ] **Step 5: Manual smoke**

```bash
cd web && npm run lint
cd web && npx vitest run src/lib/floor
```

- [ ] **Step 6: Commit**

```bash
git add web/src/components/floor web/src/app/dashboard/page.tsx
git commit -m "Add Trading Floor dashboard tab with desk board and chat."
```

---

### Task 7: Env docs + ops checklist

**Files:**
- Modify: `.env.example`

- [ ] **Step 1: Append**

```bash
# Trading Floor LLM (separate from SEA-LION signal confirm)
FLOOR_LLM_API_KEY=
FLOOR_LLM_BASE_URL=https://api.openai.com/v1
FLOOR_LLM_MODEL=
# Prefer dedicated secret; falls back to ENGINE_CRON_SECRET if empty
FLOOR_CRON_SECRET=
```

Also ensure Vercel gets the same vars. cron-job.org (or similar) hits:

`GET https://<prod-host>/api/cron/floor?secret=<FLOOR_CRON_SECRET>` every 15–30 minutes.

Apply the new schema SQL in Supabase SQL editor before first cron.

- [ ] **Step 2: Commit**

```bash
git add .env.example
git commit -m "Document Trading Floor LLM and cron env vars."
```

---

### Task 8: Verification gate

- [ ] **Step 1: Confirm signals path untouched**

```bash
git diff main...HEAD -- signals/
```

Expected: empty (or only unrelated pre-existing noise — ideally empty). Floor work must not change `signals/`.

- [ ] **Step 2: Run web floor tests**

```bash
cd web && npx vitest run src/lib/floor
```

Expected: all pass.

- [ ] **Step 3: Local/prod smoke checklist**

1. Apply schema in Supabase.
2. Set `FLOOR_LLM_*` + `FLOOR_CRON_SECRET` on Vercel.
3. Hit `/api/cron/floor?secret=...` → 200 with `saved` desks.
4. Open `/dashboard?tab=floor` as member → see cards.
5. Send a chat message → PM reply appears.
6. Open Super scalp tab → still loads signals as before.

- [ ] **Step 4: Final branch commit if any leftover polish** (only after tests green)

---

## Spec coverage check

| Spec item | Task |
|-----------|------|
| Dashboard `?tab=floor` | 6 |
| 4 desks + tones | 2–4, 6 |
| Board cron + soft-fail | 4 |
| Chat uses board pack (not 4-way debate) | 5 |
| Separate `FLOOR_LLM_*` | 2, 7 |
| New tables + RLS | 1 |
| Never write signals / touch confirm | Hard rule + Task 8 diff |
| Rate limit chat | 5 |
| Empty “warming up” | 6 |

## Placeholder scan

None intentional; implementation fills `loadContext` / `insertBrief` wiring inside Task 4 using `store.ts` REST helpers.

## Type consistency

- Desks: `macro` | `technical` | `news` | `pm`
- Tones: `bullish` | `neutral` | `cautious`
- Brief JSON: `{ tone, body }` for desks and PM chat
