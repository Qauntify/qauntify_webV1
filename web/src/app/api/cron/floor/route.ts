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
