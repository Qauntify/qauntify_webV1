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

/** Not atomic — safe only because callers always run inside a
 * beginCycle()-held lock; do not call outside that guard. */
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
