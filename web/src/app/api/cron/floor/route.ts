import { NextResponse } from "next/server";

import { floorCronAuthorized } from "@/lib/floor/auth";
import { runGoldFloorLoop } from "@/lib/floor/gold-cycle";
import { beginFloorRun, endFloorRun } from "@/lib/floor/run-control";
import { newGoldRunId } from "@/lib/floor/gold-context";

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

  const runId = newGoldRunId();
  if (!beginFloorRun(runId)) {
    return NextResponse.json({ error: "Gold hunter already running" }, { status: 409 });
  }

  try {
    await runGoldFloorLoop(runId);
    return NextResponse.json({ ok: true, runId, stopped: true });
  } catch (error) {
    const message = error instanceof Error ? error.message : "floor failed";
    return NextResponse.json({ error: message }, { status: 500 });
  } finally {
    endFloorRun();
  }
}

export async function GET(request: Request) {
  return handle(request);
}

export async function POST(request: Request) {
  return handle(request);
}
