import { NextResponse } from "next/server";

import { createClient } from "@/lib/supabase/server";
import { FLOOR_DESKS, type FloorBrief, type FloorDesk, type FloorTone } from "@/lib/floor/types";

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

export async function GET() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { data, error } = await supabase
    .from("floor_briefs")
    .select("id, desk, tone, body, run_id, created_at")
    .order("created_at", { ascending: false })
    .limit(40);
  if (error) {
    return NextResponse.json({ error: "Could not load floor board" }, { status: 500 });
  }

  const latestByDesk = new Map<FloorDesk, FloorBrief>();
  for (const row of (data ?? []) as FloorBriefRow[]) {
    if (!latestByDesk.has(row.desk)) latestByDesk.set(row.desk, mapFloorBrief(row));
  }

  const desks = FLOOR_DESKS.flatMap((desk) => {
    const brief = latestByDesk.get(desk);
    return brief ? [brief] : [];
  });

  return NextResponse.json({ desks });
}
