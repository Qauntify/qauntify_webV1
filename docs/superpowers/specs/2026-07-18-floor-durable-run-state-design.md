# Trading Floor: Durable Run State (Cron-Driven)

## Problem

The Gold AI hunter's "Run until Stop" behavior lives entirely in a single
unawaited server-side promise (`void runGoldFloorLoop(...)` in
`POST /api/admin/floor/run`), backed by module-level in-memory state in
`web/src/lib/floor/run-control.ts` (an internal `while` loop, 90s pause between
cycles). On Vercel, a serverless function is not guaranteed to keep running
once its HTTP response is sent — background work like this needs
`waitUntil`/`after()` to survive at all, and even then is capped by
`maxDuration` (300s here), never truly indefinite. In production this means
the hunt silently stops surviving somewhere between page navigations and
function recycling, contradicting the "runs forever until you press Stop"
UI copy.

A second, already-built entry point (`/api/cron/floor/route.ts`, with its
own `FLOOR_CRON_SECRET` auth) was designed for exactly this durability
problem — mirroring the pattern the Python signals engine already uses
(external cron + GitHub Actions backup, `engine.yml`) — but it's wired to
nothing and still awaits the same infinite in-process loop internally, so it
inherits the identical risk.

## Decisions

- **All run state moves out of process memory and into Supabase.** A new
  single-row table, `floor_run_state` (`id=1`), is the only source of truth
  for whether the hunter is enabled, whether a cycle is currently executing,
  and the latest cycle/phase/message — modeled on `bot_settings` for the
  Python engine.
- **The internal infinite loop is removed.** In its place: one function,
  `runOneGoldCycleIfEnabled()`, that runs *exactly one* gold-hunt cycle
  (unchanged internally — macro → technical → news → PM, in sequence) and
  returns. No internal sleep, no internal "next cycle" scheduling.
- **Cadence is external, ~2 minutes**, close to today's 90s pacing with
  headroom for LLM latency and cold starts — driven by an external cron
  service (primary) plus a GitHub Actions scheduled backup (secondary),
  mirroring `engine.yml`'s dual-trigger resilience pattern.
- **Manual Run and the cron tick call the exact same function.** Clicking
  Run arms `enabled = true` and calls `runOneGoldCycleIfEnabled()` directly,
  awaited, so the first cycle fires instantly (same feel as today). Every
  subsequent cycle comes from the external cron / GH Actions backup calling
  the identical function on their schedule.
- **Concurrency guard via `in_progress`**, not a queue: any invocation
  (manual or cron) that finds `in_progress = true` on entry exits
  immediately as a no-op. This is what prevents a cron tick and a manual
  "Run now" (or two overlapping cron backups) from firing two cycles at
  once. `in_progress` is always cleared in a `finally`, including on a
  thrown error, so a crashed cycle can't wedge the flag `true` forever.
- **Stop only prevents future cycles.** `DELETE /api/admin/floor/run` sets
  `enabled = false` and does nothing else — it does not attempt to
  interrupt a cycle already mid-execution. Since a cycle is now short (a
  handful of LLM calls, no more 90s waits baked in), Stop fully takes effect
  within one cycle's length regardless.
- **The admin log stream stops duplicating data that's already durable.**
  `floor_briefs` (written by `insertFloorBrief` on every desk response,
  already read by the public board route) becomes the log source for the
  admin UI too. The in-memory `log`/`appendFloorLog`/`FloorLogEntry` in
  `run-control.ts` — including the `state.log` field whose missing
  initialization in `beginFloorRun` caused the `TypeError: state.log is not
  iterable` crash fixed earlier this session — is removed entirely rather
  than kept in parallel with the durable version.
- **Phase semantics are unchanged conceptually**: `"macro"`/`"technical"`/
  `"news"`/`"pm"` update live within one cycle's execution exactly as today;
  `"sleeping"` now represents the gap between cron ticks (previously the
  internal `setTimeout` pause) while `enabled` is `true` but no cycle is
  currently running.

## Data model (`supabase/migrations/`)

New migration, `floor_run_state`:

```sql
create table if not exists public.floor_run_state (
    id int primary key default 1,
    enabled boolean not null default false,
    in_progress boolean not null default false,
    run_id text,
    cycle int not null default 0,
    phase text not null default 'idle',
    last_message text not null default '',
    updated_at timestamptz not null default now(),
    constraint floor_run_state_singleton check (id = 1)
);

insert into public.floor_run_state (id) values (1)
    on conflict (id) do nothing;
```

Row-level security follows the same pattern as `floor_briefs` — a read-only
policy for authenticated users (the admin UI needs to poll it); all writes
go through the service-role key (same as `insertFloorBrief`), which bypasses
RLS, so no insert/update policy is needed:

```sql
alter table public.floor_run_state enable row level security;

drop policy if exists "members read floor run state" on public.floor_run_state;
create policy "members read floor run state"
    on public.floor_run_state for select
    to authenticated
    using (true);
```

## Execution (`web/src/lib/floor/run-control.ts`, `gold-cycle.ts`)

- `run-control.ts` is rewritten from an in-memory singleton to a set of
  functions backed by REST calls to `floor_run_state` (same request-based
  pattern as `store.ts`'s `insertFloorBrief`): `readFloorRunState()`,
  `armFloorRun(runId)` (sets `enabled=true, cycle=0, run_id`),
  `disableFloorRun()` (`enabled=false`), `beginCycle()`/`endCycle(...)`
  (flip `in_progress`, bump `cycle`, update `phase`/`last_message`).
  `appendFloorLog`/`FloorLogEntry`/`MAX_LOG` are deleted along with the
  in-memory log — desk responses already reach `floor_briefs` via
  `insertFloorBrief`, so nothing needs a second, in-memory copy of the same
  data.
- `gold-cycle.ts`: `runGoldFloorLoop`'s `while`/sleep wrapper is deleted.
  `runOneGoldCycle` keeps its desk/PM sequence unchanged, minus its
  `appendFloorLog` calls (removed for the same reason above). A new
  top-level `runOneGoldCycleIfEnabled()` wraps it with the
  `enabled`/`in_progress` guard described above.

## API routes

- **`POST /api/admin/floor/run`**: `armFloorRun(runId)`, then `await
  runOneGoldCycleIfEnabled()` before responding (so the response reflects
  the first cycle's outcome, not just "started").
- **`GET /api/admin/floor/run`**: returns `readFloorRunState()` instead of
  the old in-memory `floorRunSnapshot()`.
- **`DELETE /api/admin/floor/run`**: `disableFloorRun()`.
- **`GET/POST /api/cron/floor`**: unchanged auth (`floorCronAuthorized`),
  body becomes just `await runOneGoldCycleIfEnabled()` — no more
  `beginFloorRun`/`endFloorRun`/awaiting the old infinite loop.
- **`GET /api/floor/board`** (public): `floorRunSnapshot()` calls become
  `readFloorRunState()`; the `floor_briefs` query is already durable and
  unchanged.

## Trigger infrastructure

- **External cron** (primary, ~2 min interval): hits `GET
  /api/cron/floor?secret=...` or with an `Authorization: Bearer` header —
  reuses `FLOOR_CRON_SECRET`/`floorCronAuthorized`, already implemented.
  Requires manually registering the schedule with an external cron service
  and setting `FLOOR_CRON_SECRET` in Vercel's env vars — called out as a
  manual operational step, not something code can do.
- **GitHub Actions backup** (secondary, best-effort): new
  `.github/workflows/floor.yml`, modeled on `engine.yml` — `schedule:` cron
  plus `workflow_dispatch`, single job step: `curl -X POST
  https://<domain>/api/cron/floor -H "Authorization: Bearer
  ${{ secrets.FLOOR_CRON_SECRET }}"`. No Python/Node porting — it's a plain
  HTTP call to the already-deployed route, unlike `engine.yml` which runs
  the Python engine's actual compute inside the Actions runner.

## Admin UI (`FloorRunControls.tsx`, `TradingFloor.tsx`, `GoldFloorBoard.tsx`)

- Polling behavior (2s status interval while running, 3s board interval)
  is unchanged — only the shape of what `GET /api/admin/floor/run` returns
  changes (durable state instead of in-memory snapshot), which is already
  handled by existing `FloorRunStatus`-typed response parsing.
- `GoldFloorBoard`'s `log` prop source switches from `runStatus.log`
  (removed) to fetching `floor_briefs` the same way the public board route
  already does — `TradingFloor.tsx`'s `log` fallback logic (`runStatus.log`
  vs `boardLog`) simplifies to always using the board's `floor_briefs`-backed
  log.

## Testing

- `run-control.test.ts` is rewritten against the new Supabase-backed
  functions (mocked HTTP calls, matching how other `store.ts`-style
  persistence is tested elsewhere): `enabled=false` →
  `runOneGoldCycleIfEnabled()` no-ops without calling `runOneGoldCycle`;
  `in_progress=true` on entry → also no-ops; a thrown error inside
  `runOneGoldCycle` still clears `in_progress` (`finally` behavior).
- `TradingFloor.test.tsx`/`GoldFloorBoard` tests updated for the log source
  change. The pre-existing, unrelated `scrollIntoView is not a function`
  jsdom failure in `GoldFloorBoard.tsx` is out of scope here (flagged
  separately, not touched by this work).

## Out of scope

- Mid-cycle cancellation on Stop (cycles are short enough that this isn't
  needed; revisit only if cycles grow much longer).
- Any change to `runOneGoldCycle`'s actual desk/PM logic, LLM prompts, or
  Telegram alerting — this spec only changes *how the loop is kept alive*,
  not what each cycle does.
- Historical run analytics / a `floor_runs` table capturing per-cycle
  outcomes over time (the Python engine has `engine_runs` for this) — could
  be a natural follow-up, not needed for "Run persists until Stop" to work.
