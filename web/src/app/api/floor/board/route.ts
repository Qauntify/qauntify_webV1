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
