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
