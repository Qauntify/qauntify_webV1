import type { FloorDesk, FloorTone } from "./types";
import { floorSupabaseConfig, floorSupabaseHeaders } from "./supabase-config";

export async function insertFloorBrief(input: {
  desk: FloorDesk;
  tone: FloorTone;
  body: string;
  runId: string;
}): Promise<void> {
  const cfg = floorSupabaseConfig();
  if (!cfg) throw new Error("Supabase service-role configuration is unavailable");

  const response = await fetch(`${cfg.url}/rest/v1/floor_briefs`, {
    method: "POST",
    headers: { ...floorSupabaseHeaders(cfg.serviceKey), Prefer: "return=minimal" },
    body: JSON.stringify({
      desk: input.desk,
      tone: input.tone,
      body: input.body,
      run_id: input.runId,
    }),
  });
  if (!response.ok) {
    throw new Error(`Could not insert floor brief (HTTP ${response.status})`);
  }
}
