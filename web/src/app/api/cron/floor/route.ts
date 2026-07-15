import { NextResponse } from "next/server";

import { floorCronAuthorized } from "@/lib/floor/auth";
import { runFloorBoardCycle } from "@/lib/floor/board";
import { insertFloorBrief, loadFloorContext } from "@/lib/floor/store";

export const dynamic = "force-dynamic";
export const maxDuration = 60;

async function handle(request: Request) {
  const secret = process.env.FLOOR_CRON_SECRET || process.env.ENGINE_CRON_SECRET || "";
  if (!floorCronAuthorized(request, secret)) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  try {
    const result = await runFloorBoardCycle({
      loadContext: loadFloorContext,
      insertBrief: insertFloorBrief,
    });
    return NextResponse.json({ ok: true, ...result });
  } catch (error) {
    const message = error instanceof Error ? error.message : "floor failed";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}

export async function GET(request: Request) {
  return handle(request);
}

export async function POST(request: Request) {
  return handle(request);
}
