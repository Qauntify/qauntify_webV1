import { randomUUID } from "crypto";

import { NextResponse } from "next/server";

import { requireAdminApi } from "@/lib/admin-api-guard";
import { runGoldFloorLoop } from "@/lib/floor/gold-cycle";
import {
  beginFloorRun,
  endFloorRun,
  floorRunSnapshot,
  requestFloorStop,
} from "@/lib/floor/run-control";

export const dynamic = "force-dynamic";
export const maxDuration = 300;

export async function GET() {
  const denied = await requireAdminApi();
  if (denied) return denied;

  return NextResponse.json(floorRunSnapshot());
}

export async function POST() {
  const denied = await requireAdminApi();
  if (denied) return denied;

  const runId = randomUUID();
  if (!beginFloorRun(runId)) {
    return NextResponse.json(
      { error: "Gold hunter is already running." },
      { status: 409 },
    );
  }

  void runGoldFloorLoop(runId)
    .catch(() => {
      // loop errors are surfaced via lastMessage on the next poll
    })
    .finally(() => {
      endFloorRun();
    });

  return NextResponse.json({
    ok: true,
    started: true,
    runId,
    message: "Gold hunter started. It will run until you press Stop.",
  });
}

export async function DELETE() {
  const denied = await requireAdminApi();
  if (denied) return denied;
  requestFloorStop();
  return NextResponse.json({ ok: true, ...floorRunSnapshot() });
}
