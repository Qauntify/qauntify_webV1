// Reads AI War Room debate transcripts from Supabase (public read-only).

export type DebateMessage = {
  agent: string;
  avatar: string;
  message: string;
};

export type Debate = {
  id: string;
  symbol: string;
  timeframe: string;
  direction: "long" | "short";
  transcript: DebateMessage[];
  managerVerdict: string;
  managerConfidence: number;
  createdAt: string;
};

function supabaseConfig(): { url: string; anonKey: string } | null {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !anonKey) return null;
  return { url: url.replace(/\/$/, ""), anonKey };
}

function parseMessages(raw: unknown): DebateMessage[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .filter((m): m is Record<string, unknown> => typeof m === "object" && m !== null)
    .map((m) => ({
      agent: String(m.agent ?? ""),
      avatar: String(m.avatar ?? "🤖"),
      message: String(m.message ?? ""),
    }))
    .filter((m) => m.agent && m.message);
}

function parseDebate(row: Record<string, unknown>): Debate | null {
  if (!row || typeof row.id !== "string") return null;
  const direction = row.direction === "short" ? "short" : "long";
  const confidence = Number(row.manager_confidence);
  return {
    id: row.id,
    symbol: String(row.symbol ?? ""),
    timeframe: String(row.timeframe ?? ""),
    direction,
    transcript: parseMessages(row.transcript),
    managerVerdict: String(row.manager_verdict ?? "caution"),
    managerConfidence: Number.isFinite(confidence) ? confidence : 0,
    createdAt: String(row.created_at ?? ""),
  };
}

export async function getDebates(limit = 8): Promise<Debate[]> {
  const config = supabaseConfig();
  if (!config) return [];
  try {
    const query = new URLSearchParams({
      select: "*",
      order: "created_at.desc",
      limit: String(limit),
    });
    const response = await fetch(
      `${config.url}/rest/v1/agent_debates?${query.toString()}`,
      {
        headers: {
          apikey: config.anonKey,
          Authorization: `Bearer ${config.anonKey}`,
        },
        cache: "no-store",
      },
    );
    if (!response.ok) return [];
    const rows = (await response.json()) as Record<string, unknown>[];
    return rows
      .map(parseDebate)
      .filter((d): d is Debate => d !== null && d.transcript.length > 0);
  } catch {
    return [];
  }
}
