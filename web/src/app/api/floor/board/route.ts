import { NextResponse } from "next/server";

import { floorRunSnapshot } from "@/lib/floor/run-control";
import { FLOOR_DESKS, GOLD_SYMBOL, type FloorBrief, type FloorDesk, type FloorTone } from "@/lib/floor/types";
import { isAdminEmail } from "@/lib/supabase/admin";
import { createClient } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

type FloorBriefRow = {
  id: string;
  desk: FloorDesk;
  tone: FloorTone;
  body: string;
  run_id: string;
  created_at: string;
};

function mapFloorBrief(row: FloorBriefRow): FloorBrief {
  return {
    id: row.id,
    desk: row.desk,
    tone: row.tone,
    body: row.body,
    runId: row.run_id,
    createdAt: row.created_at,
  };
}

function scanLineFromSnapshot(): string {
  const snapshot = floorRunSnapshot();
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
    .select("id, desk, tone, body, run_id, created_at")
    .order("created_at", { ascending: false })
    .limit(40);

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

  const latestByDesk = new Map<FloorDesk, FloorBrief>();
  for (const row of (data ?? []) as FloorBriefRow[]) {
    if (!latestByDesk.has(row.desk)) latestByDesk.set(row.desk, mapFloorBrief(row));
  }

  const desks = FLOOR_DESKS.flatMap((desk) => {
    const brief = latestByDesk.get(desk);
    return brief ? [brief] : [];
  });

  const snapshot = floorRunSnapshot();

  return NextResponse.json({
    symbol: GOLD_SYMBOL,
    desks,
    lastSignal: snapshot.lastSignal,
    scanLine: scanLineFromSnapshot(),
  });
}
