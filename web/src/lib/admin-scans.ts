/** Pure helpers for Admin → Scans (engine_runs history). */

export type EngineOutcome = {
  symbol: string;
  timeframe: string | null;
  status: string;
  extra: string;
};

export type EngineRunSummary = {
  id: string;
  runId: string;
  timeframe: string;
  storedCount: number;
  outcomes: EngineOutcome[];
  finishedAt: string;
};

export function parseEngineOutcomes(raw: unknown): EngineOutcome[] {
  if (!Array.isArray(raw)) return [];
  return raw.flatMap((item) => {
    if (!item || typeof item !== "object") return [];
    const row = item as Record<string, unknown>;
    const symbol = typeof row.symbol === "string" ? row.symbol : "";
    if (!symbol) return [];
    return [
      {
        symbol,
        timeframe:
          typeof row.timeframe === "string" && row.timeframe
            ? row.timeframe
            : null,
        status: typeof row.status === "string" ? row.status : "UNKNOWN",
        extra: typeof row.extra === "string" ? row.extra : "",
      },
    ];
  });
}

export function countOutcomesByStatus(
  outcomes: EngineOutcome[],
): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const o of outcomes) {
    counts[o.status] = (counts[o.status] ?? 0) + 1;
  }
  return counts;
}

/** Window around a run finish so AI responses can be correlated by time. */
export function aiResponsesWindowForRun(finishedAt: string): {
  since: string;
  until: string;
} {
  const end = new Date(finishedAt);
  if (Number.isNaN(end.getTime())) {
    return { since: finishedAt, until: finishedAt };
  }
  const start = new Date(end.getTime() - 20 * 60 * 1000);
  const until = new Date(end.getTime() + 2 * 60 * 1000);
  return { since: start.toISOString(), until: until.toISOString() };
}

export function aiResponsesHrefForRun(
  finishedAt: string,
  extra: { symbol?: string; timeframe?: string } = {},
): string {
  const { since, until } = aiResponsesWindowForRun(finishedAt);
  const params = new URLSearchParams();
  params.set("since", since);
  params.set("until", until);
  if (extra.symbol) params.set("symbol", extra.symbol);
  if (extra.timeframe) params.set("timeframe", extra.timeframe);
  return `/admin/ai/responses?${params.toString()}`;
}
