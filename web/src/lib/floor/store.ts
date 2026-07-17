import type { FloorDesk, FloorTone } from "./types";

type Config = { url: string; serviceKey: string };

function config(): Config | null {
  const url = (process.env.NEXT_PUBLIC_SUPABASE_URL || process.env.SUPABASE_URL)?.trim();
  const serviceKey = process.env.SUPABASE_SERVICE_ROLE_KEY?.trim();
  if (!url || !serviceKey) return null;
  return { url: url.replace(/\/$/, ""), serviceKey };
}

function headers(serviceKey: string): HeadersInit {
  return {
    apikey: serviceKey,
    Authorization: `Bearer ${serviceKey}`,
    "Content-Type": "application/json",
  };
}

export async function insertFloorBrief(input: {
  desk: FloorDesk;
  tone: FloorTone;
  body: string;
  runId: string;
}): Promise<void> {
  const cfg = config();
  if (!cfg) throw new Error("Supabase service-role configuration is unavailable");

  const response = await fetch(`${cfg.url}/rest/v1/floor_briefs`, {
    method: "POST",
    headers: { ...headers(cfg.serviceKey), Prefer: "return=minimal" },
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
