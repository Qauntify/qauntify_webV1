/** Pure helpers for Admin → AI responses filters. */

export type AiEventKindFilter = "confirm" | "reject" | "no_setup";
export type AiEventTimeframeFilter = "5m" | "15m" | "1h";

export type AiEventFilters = {
  symbol?: string;
  timeframe?: AiEventTimeframeFilter;
  kind?: AiEventKindFilter;
  since?: string;
  until?: string;
};

const TIMEFRAMES = new Set<AiEventTimeframeFilter>(["5m", "15m", "1h"]);
const KINDS = new Set<AiEventKindFilter>(["confirm", "reject", "no_setup"]);

export function parseAiEventFilters(
  params: Record<string, string | undefined>,
): AiEventFilters {
  const filters: AiEventFilters = {};

  const symbol = (params.symbol ?? "").trim().toUpperCase();
  if (symbol) filters.symbol = symbol;

  const timeframe = params.timeframe;
  if (timeframe && TIMEFRAMES.has(timeframe as AiEventTimeframeFilter)) {
    filters.timeframe = timeframe as AiEventTimeframeFilter;
  }

  const kind = params.kind;
  if (kind && KINDS.has(kind as AiEventKindFilter)) {
    filters.kind = kind as AiEventKindFilter;
  }

  if (params.since && !Number.isNaN(Date.parse(params.since))) {
    filters.since = new Date(params.since).toISOString();
  }
  if (params.until && !Number.isNaN(Date.parse(params.until))) {
    filters.until = new Date(params.until).toISOString();
  }

  return filters;
}

/** PostgREST filter query fragment (leading & when non-empty). */
export function aiEventsFilterQuery(filters: AiEventFilters): string {
  const parts: string[] = [];
  if (filters.symbol) {
    parts.push(`symbol=eq.${encodeURIComponent(filters.symbol)}`);
  }
  if (filters.timeframe) {
    parts.push(`timeframe=eq.${encodeURIComponent(filters.timeframe)}`);
  }
  if (filters.kind) {
    parts.push(`kind=eq.${encodeURIComponent(filters.kind)}`);
  }
  if (filters.since) {
    parts.push(`created_at=gte.${encodeURIComponent(filters.since)}`);
  }
  if (filters.until) {
    parts.push(`created_at=lte.${encodeURIComponent(filters.until)}`);
  }
  return parts.length ? `&${parts.join("&")}` : "";
}

export function aiResponsesHref(
  filters: AiEventFilters,
  page = 1,
): string {
  const params = new URLSearchParams();
  if (filters.symbol) params.set("symbol", filters.symbol);
  if (filters.timeframe) params.set("timeframe", filters.timeframe);
  if (filters.kind) params.set("kind", filters.kind);
  if (filters.since) params.set("since", filters.since);
  if (filters.until) params.set("until", filters.until);
  if (page > 1) params.set("page", String(page));
  const qs = params.toString();
  return qs ? `/admin/ai/responses?${qs}` : "/admin/ai/responses";
}

export function aiResponsesExtraParams(
  filters: AiEventFilters,
): Record<string, string> {
  const extra: Record<string, string> = {};
  if (filters.symbol) extra.symbol = filters.symbol;
  if (filters.timeframe) extra.timeframe = filters.timeframe;
  if (filters.kind) extra.kind = filters.kind;
  if (filters.since) extra.since = filters.since;
  if (filters.until) extra.until = filters.until;
  return extra;
}
