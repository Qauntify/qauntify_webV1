// Server-only admin helpers: service-role calls to Supabase Auth admin API
// and the bot_settings table. Import only from server components/actions —
// SUPABASE_SERVICE_ROLE_KEY must never reach the browser.

import {
  aiEventsFilterQuery,
  type AiEventFilters,
} from "@/lib/admin-ai-filters";
import { parseEngineOutcomes } from "@/lib/admin-scans";
import type { SignalRow } from "@/lib/outcome-rules";

export type AdminUser = {
  id: string;
  email: string;
  createdAt: string;
  lastSignInAt: string | null;
};

export type BotSettings = {
  symbols: string[];
  minAlertConfidence: number;
  minStoreConfidence: number;
  signalStrategy: string;
};

export const SIGNAL_STRATEGIES = [
  {
    id: "ema_cross",
    label: "EMA crossover (RSI + MACD filters)",
    description: "Current default — EMA 9/21 cross with RSI and MACD confirmation.",
  },
  {
    id: "ict_smc",
    label: "ICT / SMC (liquidity sweep + CHoCH)",
    description:
      "Smart-money style — sweep beyond a swing level, then a structure shift.",
  },
  {
    id: "sr_zone",
    label: "Support / Resistance (bounce)",
    description:
      "Buy support / sell resistance on a confirmation candle at a tested zone. Favours ranging markets.",
  },
  {
    id: "bbma_reentry",
    label: "BBMA Re-entry (continuation)",
    description:
      "After a CSAK or CSM direction candle, price pulls back into the MA5/MA10 zone and holds it; entry on the next candle. Backtested at −0.14R per trade over 8.87 years.",
  },
  {
    id: "bbma_extreme",
    label: "BBMA Extreme (reversal)",
    description:
      "MA5 escapes the Bollinger band, then price rejects back inside and retests MA5. Backtested at −0.15R per trade over 8.87 years.",
  },
] as const;

export type AiEvent = {
  id: string;
  symbol: string;
  timeframe: string;
  kind: "confirm" | "reject" | "no_setup";
  direction: "long" | "short" | null;
  entry: number | null;
  stopLoss: number | null;
  takeProfit: number | null;
  confidence: number | null;
  rationale: string;
  indicators: unknown;
  newsHeadlines: unknown;
  createdAt: string;
};

type AiEventRow = {
  id: string;
  symbol: string;
  timeframe: string;
  kind: string;
  direction: string | null;
  entry: number | null;
  stop_loss: number | null;
  take_profit: number | null;
  confidence: number | null;
  rationale: string;
  indicators: unknown;
  news_headlines: unknown;
  created_at: string;
};

function parseAiEventKind(value: string): AiEvent["kind"] | null {
  if (value === "confirm" || value === "reject" || value === "no_setup") {
    return value;
  }
  return null;
}

function parseAiEventDirection(value: string | null): AiEvent["direction"] {
  if (value === "long" || value === "short") return value;
  return null;
}

function config(): { url: string; serviceKey: string } | null {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const serviceKey = process.env.SUPABASE_SERVICE_ROLE_KEY;
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

const READ_CACHE = { cache: "no-store" as const };

export { isAdminEmail } from "@/lib/admin-emails";

export async function listUsers(): Promise<AdminUser[] | null> {
  const cfg = config();
  if (!cfg) return null;
  try {
    const response = await fetch(
      `${cfg.url}/auth/v1/admin/users?per_page=200`,
      { headers: headers(cfg.serviceKey), ...READ_CACHE },
    );
    if (!response.ok) return null;
    const body = await response.json();
    if (!Array.isArray(body.users)) return null;
    return body.users.map(
      (u: {
        id: string;
        email?: string;
        created_at: string;
        last_sign_in_at?: string | null;
      }) => ({
        id: u.id,
        email: u.email ?? "(no email)",
        createdAt: u.created_at,
        lastSignInAt: u.last_sign_in_at ?? null,
      }),
    );
  } catch {
    return null;
  }
}

export async function getUserEmail(id: string): Promise<string | null> {
  const cfg = config();
  if (!cfg) return null;
  try {
    const response = await fetch(`${cfg.url}/auth/v1/admin/users/${id}`, {
      headers: headers(cfg.serviceKey),
      ...READ_CACHE,
    });
    if (!response.ok) return null;
    const body = await response.json();
    return typeof body.email === "string" ? body.email : null;
  } catch {
    return null;
  }
}

export async function deleteUser(id: string): Promise<boolean> {
  const cfg = config();
  if (!cfg) return false;
  try {
    const response = await fetch(`${cfg.url}/auth/v1/admin/users/${id}`, {
      method: "DELETE",
      headers: headers(cfg.serviceKey),
    });
    return response.ok;
  } catch {
    return false;
  }
}

// The service-role JWT doubles as an access token that bypasses RLS, so the
// admin overview can reuse the public signals fetchers with full visibility.
export function serviceRoleToken(): string | undefined {
  return process.env.SUPABASE_SERVICE_ROLE_KEY || undefined;
}

export async function getBotSettings(): Promise<BotSettings | null> {
  const cfg = config();
  if (!cfg) return null;
  try {
    const response = await fetch(
      `${cfg.url}/rest/v1/bot_settings?id=eq.1&select=symbols,min_alert_confidence,min_store_confidence,signal_strategy`,
      { headers: headers(cfg.serviceKey), ...READ_CACHE },
    );
    if (!response.ok) return null;
    const rows = await response.json();
    const row = Array.isArray(rows) ? rows[0] : null;
    if (!row || !Array.isArray(row.symbols)) return null;
    return {
      symbols: row.symbols,
      minAlertConfidence: row.min_alert_confidence,
      minStoreConfidence: row.min_store_confidence ?? 0,
      signalStrategy: row.signal_strategy ?? "ema_cross",
    };
  } catch {
    return null;
  }
}

export async function updateBotSettings(
  settings: BotSettings,
): Promise<boolean> {
  const cfg = config();
  if (!cfg) return false;
  try {
    const response = await fetch(`${cfg.url}/rest/v1/bot_settings?id=eq.1`, {
      method: "PATCH",
      headers: { ...headers(cfg.serviceKey), Prefer: "return=minimal" },
      body: JSON.stringify({
        symbols: settings.symbols,
        min_alert_confidence: settings.minAlertConfidence,
        min_store_confidence: settings.minStoreConfidence,
        signal_strategy: settings.signalStrategy,
        updated_at: new Date().toISOString(),
      }),
    });
    return response.ok;
  } catch {
    return false;
  }
}

function mapAiEventRows(rows: AiEventRow[]): AiEvent[] {
  if (!Array.isArray(rows)) return [];
  return rows.flatMap((r) => {
    const kind = parseAiEventKind(r.kind);
    if (!kind) return [];
    return [{
      id: String(r.id),
      symbol: String(r.symbol),
      timeframe: String(r.timeframe),
      kind,
      direction: parseAiEventDirection(r.direction),
      entry: typeof r.entry === "number" ? r.entry : null,
      stopLoss: typeof r.stop_loss === "number" ? r.stop_loss : null,
      takeProfit: typeof r.take_profit === "number" ? r.take_profit : null,
      confidence: typeof r.confidence === "number" ? r.confidence : null,
      rationale: String(r.rationale ?? ""),
      indicators: r.indicators,
      newsHeadlines: r.news_headlines,
      createdAt: String(r.created_at),
    }];
  });
}

function parseContentRangeTotal(header: string | null): number | null {
  if (!header) return null;
  const match = header.match(/\d+-\d+\/(\d+|\*)/);
  if (!match || match[1] === "*") return null;
  const total = Number(match[1]);
  return Number.isFinite(total) ? total : null;
}

export const AI_EVENTS_PAGE_SIZE = 20;

export type AiEventsPage = {
  events: AiEvent[];
  page: number;
  pageSize: number;
  total: number;
  totalPages: number;
};

export async function listAiEventsPage(
  page = 1,
  pageSize = AI_EVENTS_PAGE_SIZE,
  filters: AiEventFilters = {},
): Promise<AiEventsPage | null> {
  const cfg = config();
  if (!cfg) return null;
  const safePage = Number.isInteger(page) && page > 0 ? page : 1;
  const offset = (safePage - 1) * pageSize;
  const rangeEnd = offset + pageSize - 1;
  const filterQuery = aiEventsFilterQuery(filters);
  try {
    const response = await fetch(
      `${cfg.url}/rest/v1/ai_events?select=*&order=created_at.desc${filterQuery}`,
      {
        headers: {
          ...headers(cfg.serviceKey),
          Range: `${offset}-${rangeEnd}`,
          Prefer: "count=exact",
        },
        ...READ_CACHE,
      },
    );
    if (!response.ok) return null;
    const rows = (await response.json()) as AiEventRow[];
    const events = mapAiEventRows(rows);
    const total = parseContentRangeTotal(
      response.headers.get("content-range"),
    ) ?? events.length;
    const totalPages = Math.max(1, Math.ceil(total / pageSize) || 1);
    return {
      events,
      page: Math.min(safePage, totalPages),
      pageSize,
      total,
      totalPages,
    };
  } catch {
    return null;
  }
}

export async function listAiEvents(limit = 50): Promise<AiEvent[] | null> {
  const page = await listAiEventsPage(1, limit);
  return page?.events ?? null;
}

export type EngineRun = {
  id: string;
  runId: string;
  timeframe: string;
  storedCount: number;
  outcomes: unknown;
  finishedAt: string;
};

type EngineRunRow = {
  id: string;
  run_id: string;
  timeframe: string;
  stored_count: number;
  outcomes: unknown;
  finished_at: string;
};

function mapEngineRunRow(row: EngineRunRow): EngineRun {
  return {
    id: String(row.id),
    runId: String(row.run_id),
    timeframe: String(row.timeframe),
    storedCount: Number(row.stored_count ?? 0),
    outcomes: row.outcomes,
    finishedAt: String(row.finished_at),
  };
}

export async function latestEngineRun(): Promise<EngineRun | null> {
  const cfg = config();
  if (!cfg) return null;
  try {
    const response = await fetch(
      `${cfg.url}/rest/v1/engine_runs?select=*` +
        `&order=finished_at.desc&limit=1`,
      { headers: headers(cfg.serviceKey), ...READ_CACHE },
    );
    if (!response.ok) return null;
    const rows = (await response.json()) as EngineRunRow[];
    const row = Array.isArray(rows) ? rows[0] : null;
    if (!row) return null;
    return mapEngineRunRow(row);
  } catch {
    return null;
  }
}

export const ENGINE_RUNS_PAGE_SIZE = 20;

export type EngineRunsPage = {
  runs: EngineRun[];
  page: number;
  pageSize: number;
  total: number;
  totalPages: number;
};

export async function listEngineRunsPage(
  page = 1,
  pageSize = ENGINE_RUNS_PAGE_SIZE,
): Promise<EngineRunsPage | null> {
  const cfg = config();
  if (!cfg) return null;
  const safePage = Number.isInteger(page) && page > 0 ? page : 1;
  const offset = (safePage - 1) * pageSize;
  const rangeEnd = offset + pageSize - 1;
  try {
    const response = await fetch(
      `${cfg.url}/rest/v1/engine_runs?select=*&order=finished_at.desc`,
      {
        headers: {
          ...headers(cfg.serviceKey),
          Range: `${offset}-${rangeEnd}`,
          Prefer: "count=exact",
        },
        ...READ_CACHE,
      },
    );
    if (!response.ok) return null;
    const rows = (await response.json()) as EngineRunRow[];
    const runs = Array.isArray(rows) ? rows.map(mapEngineRunRow) : [];
    const total =
      parseContentRangeTotal(response.headers.get("content-range")) ??
      runs.length;
    const totalPages = Math.max(1, Math.ceil(total / pageSize) || 1);
    return {
      runs,
      page: Math.min(safePage, totalPages),
      pageSize,
      total,
      totalPages,
    };
  } catch {
    return null;
  }
}

/** Re-export for admin pages that want typed outcomes without a second import. */
export { parseEngineOutcomes };


export type EngineStatus = {
  runId: string;
  timeframe: string;
  storedCount: number;
  finishedAt: string;
  isHealthy: boolean;
  ageMinutes: number;
};

type EngineStatusRow = {
  run_id: string;
  timeframe: string;
  stored_count: number;
  finished_at: string;
  is_healthy: boolean;
  age_minutes: number;
};

export async function getEngineStatus(): Promise<EngineStatus | null> {
  const cfg = config();
  if (!cfg) return null;
  try {
    const response = await fetch(`${cfg.url}/rest/v1/engine_status?select=*`, {
      headers: headers(cfg.serviceKey),
      ...READ_CACHE,
    });
    if (!response.ok) return null;
    const rows = (await response.json()) as EngineStatusRow[];
    const row = Array.isArray(rows) ? rows[0] : null;
    if (!row) return null;
    return {
      runId: String(row.run_id),
      timeframe: String(row.timeframe),
      storedCount: Number(row.stored_count ?? 0),
      finishedAt: String(row.finished_at),
      isHealthy: Boolean(row.is_healthy),
      ageMinutes: Number(row.age_minutes ?? 0),
    };
  } catch {
    return null;
  }
}

export type XauScanStatus = {
  runId: string;
  signalFound: boolean;
  finishedAt: string;
  isHealthy: boolean;
  ageMinutes: number;
};

type XauScanStatusRow = {
  run_id: string;
  signal_found: boolean;
  finished_at: string;
  is_healthy: boolean;
  age_minutes: number;
};

export async function getXauScanStatus(): Promise<XauScanStatus | null> {
  const cfg = config();
  if (!cfg) return null;
  try {
    const response = await fetch(`${cfg.url}/rest/v1/xau_scan_status?select=*`, {
      headers: headers(cfg.serviceKey),
      ...READ_CACHE,
    });
    if (!response.ok) return null;
    const rows = (await response.json()) as XauScanStatusRow[];
    const row = Array.isArray(rows) ? rows[0] : null;
    if (!row) return null;
    return {
      runId: String(row.run_id),
      signalFound: Boolean(row.signal_found),
      finishedAt: String(row.finished_at),
      isHealthy: Boolean(row.is_healthy),
      ageMinutes: Number(row.age_minutes ?? 0),
    };
  } catch {
    return null;
  }
}

export async function deleteSignal(id: string): Promise<boolean> {
  const cfg = config();
  if (!cfg) return false;
  try {
    const response = await fetch(`${cfg.url}/rest/v1/signals?id=eq.${id}`, {
      method: "DELETE",
      headers: headers(cfg.serviceKey),
    });
    return response.ok;
  } catch {
    return false;
  }
}

const OPEN_SIGNAL_COLUMNS =
  "id,symbol,timeframe,direction,entry,stop_loss,take_profit,take_profit_1," +
  "take_profit_2,take_profit_3,tp1_hit_at,tp2_hit_at,tp3_hit_at,status,created_at";

const OPEN_SIGNALS_CACHE_TTL_MS = 3000;
const openSignalsCache = new Map<string, { rows: SignalRow[]; expiresAt: number }>();

/** Open/tp1/tp2 rows for one symbol — same filter shape as
 * signals/storage.py:list_open_signals (shadow rows included on purpose,
 * for parity: the Python cron path tracks their outcomes too).
 *
 * Cached per-symbol for a few seconds: the MT5 tick route can call this
 * several times a second, and this mirrors the in-memory cache
 * signals/realtime_watcher.py already keeps for the same reason — without
 * it, every tick would be its own Supabase round-trip. Best-effort only
 * (each serverless instance has its own cache, and cold starts miss it) —
 * callers that successfully claim an event must call
 * invalidateOpenSignalsCache so the next tick sees the fresh status instead
 * of possibly missing a second level crossed moments later. */
export async function getOpenSignalsForSymbol(
  symbol: string,
): Promise<SignalRow[] | null> {
  const cached = openSignalsCache.get(symbol);
  if (cached && cached.expiresAt > Date.now()) return cached.rows;

  const cfg = config();
  if (!cfg) return null;
  try {
    const response = await fetch(
      `${cfg.url}/rest/v1/signals?symbol=eq.${encodeURIComponent(symbol)}` +
        `&status=in.(open,tp1_hit,tp2_hit)&closed_at=is.null` +
        `&select=${OPEN_SIGNAL_COLUMNS}&order=created_at.asc`,
      { headers: headers(cfg.serviceKey), ...READ_CACHE },
    );
    if (!response.ok) return null;
    const rows = (await response.json()) as SignalRow[];
    openSignalsCache.set(symbol, { rows, expiresAt: Date.now() + OPEN_SIGNALS_CACHE_TTL_MS });
    return rows;
  } catch {
    return null;
  }
}

/** Drops the cached open-signals list for one symbol — call after
 * successfully claiming an event so the next tick re-fetches fresh instead
 * of re-evaluating a now-stale status for up to OPEN_SIGNALS_CACHE_TTL_MS. */
export function invalidateOpenSignalsCache(symbol: string): void {
  openSignalsCache.delete(symbol);
}

/** Upsert the latest MT5 broker quote so the Python engine can require a
 * fresh mid and snap gold entries to the broker. Prefers `mt5_last_ticks`;
 * falls back to Storage JSON when the migration is not applied yet. */
export async function upsertMt5LastTick(
  symbol: string,
  quotes: number | { bid: number; ask: number; mid?: number },
  tickTimeUnixSec: number,
): Promise<boolean> {
  const cfg = config();
  if (!cfg) return false;
  const canon = symbol.trim().toUpperCase();
  let bid: number;
  let ask: number;
  let mid: number;
  if (typeof quotes === "number") {
    bid = ask = mid = quotes;
  } else {
    bid = quotes.bid;
    ask = quotes.ask;
    mid = quotes.mid ?? (bid + ask) / 2;
  }
  const payload = {
    symbol: canon,
    price: mid,
    bid,
    ask,
    mid,
    tick_time: new Date(tickTimeUnixSec * 1000).toISOString(),
    updated_at: new Date().toISOString(),
  };
  try {
    const response = await fetch(`${cfg.url}/rest/v1/mt5_last_ticks`, {
      method: "POST",
      headers: {
        ...headers(cfg.serviceKey),
        Prefer: "resolution=merge-duplicates,return=minimal",
      },
      body: JSON.stringify(payload),
    });
    if (response.ok || response.status === 201) return true;
    const detail = (await response.json().catch(() => null)) as { code?: string } | null;
    if (response.status !== 404 && detail?.code !== "PGRST205") {
      return false;
    }
  } catch {
    // fall through to Storage
  }
  try {
    const path = `mt5-last-ticks/${canon}.json`;
    const response = await fetch(
      `${cfg.url}/storage/v1/object/signal-charts/${path}`,
      {
        method: "POST",
        headers: {
          ...headers(cfg.serviceKey),
          "Content-Type": "application/json",
          "x-upsert": "true",
        },
        body: JSON.stringify(payload),
      },
    );
    return response.ok || response.status === 200 || response.status === 201;
  } catch {
    return false;
  }
}

export type Mt5CandleBar = {
  open_time: number; // unix seconds
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
};

const MT5_CANDLE_MAX_BARS = 14_400; // ~10 days of M1 for 5m/15m/1h resample

/** Merge closed MT5 bars into a Storage ring buffer used by the Python
 * gold 1m detector. Soft-fails if Storage is unreachable. */
export async function mergeMt5Candles(
  symbol: string,
  timeframe: string,
  incoming: Mt5CandleBar[],
): Promise<boolean> {
  const cfg = config();
  if (!cfg || incoming.length === 0) return false;
  const canon = symbol.trim().toUpperCase();
  const path = `mt5-candles/${canon}-${timeframe}.json`;
  let existing: Mt5CandleBar[] = [];
  try {
    const get = await fetch(
      `${cfg.url}/storage/v1/object/signal-charts/${path}`,
      { headers: headers(cfg.serviceKey) },
    );
    if (get.ok) {
      const data = (await get.json()) as { candles?: Mt5CandleBar[] } | Mt5CandleBar[];
      existing = Array.isArray(data) ? data : (data.candles ?? []);
    }
  } catch {
    existing = [];
  }

  const byTime = new Map<number, Mt5CandleBar>();
  for (const c of existing) {
    if (c && Number.isFinite(c.open_time)) byTime.set(Number(c.open_time), c);
  }
  for (const c of incoming) {
    byTime.set(Number(c.open_time), {
      open_time: Number(c.open_time),
      open: Number(c.open),
      high: Number(c.high),
      low: Number(c.low),
      close: Number(c.close),
      volume: Number(c.volume ?? 0),
    });
  }
  const merged = [...byTime.values()]
    .sort((a, b) => a.open_time - b.open_time)
    .slice(-MT5_CANDLE_MAX_BARS);

  try {
    const response = await fetch(
      `${cfg.url}/storage/v1/object/signal-charts/${path}`,
      {
        method: "POST",
        headers: {
          ...headers(cfg.serviceKey),
          "Content-Type": "application/json",
          "x-upsert": "true",
        },
        body: JSON.stringify({
          symbol: canon,
          timeframe,
          updated_at: new Date().toISOString(),
          candles: merged,
        }),
      },
    );
    return response.ok || response.status === 200 || response.status === 201;
  } catch {
    return false;
  }
}

/** True when a non-shadow open/tp1/tp2 signal already exists for symbol+tf.
 * Mirrors signals/storage.py:open_symbols_for_timeframe for one pair. */
export async function hasOpenLiveSignal(
  symbol: string,
  timeframe: string,
): Promise<boolean | null> {
  const cfg = config();
  if (!cfg) return null;
  try {
    const response = await fetch(
      `${cfg.url}/rest/v1/signals?symbol=eq.${encodeURIComponent(symbol)}` +
        `&timeframe=eq.${encodeURIComponent(timeframe)}` +
        `&status=in.(open,tp1_hit,tp2_hit)&closed_at=is.null` +
        `&shadow=is.false&select=id&limit=1`,
      { headers: headers(cfg.serviceKey), ...READ_CACHE },
    );
    if (!response.ok) return null;
    const rows = (await response.json()) as unknown[];
    return Array.isArray(rows) && rows.length > 0;
  } catch {
    return null;
  }
}

export type LiveSignalInsert = {
  id: string;
  symbol: string;
  timeframe: string;
  direction: string;
  entry: number;
  stop_loss: number;
  take_profit: number;
  take_profit_1: number;
  take_profit_2: number;
  take_profit_3: number;
  confidence: number;
  rationale: string;
  indicators: Record<string, unknown>;
  news_headlines: unknown[];
  created_at: string;
  shadow: boolean;
  experiment: string | null;
};

/** Insert a live (delivered) signal row — MT5 EA publish path. */
export async function insertLiveSignal(
  row: LiveSignalInsert,
): Promise<boolean> {
  const cfg = config();
  if (!cfg) return false;
  try {
    const response = await fetch(`${cfg.url}/rest/v1/signals`, {
      method: "POST",
      headers: { ...headers(cfg.serviceKey), Prefer: "return=minimal" },
      body: JSON.stringify(row),
    });
    return response.ok || response.status === 201;
  } catch {
    return false;
  }
}

const SIGNAL_CHART_BUCKET = "signal-charts";

/** True when a signals row with this id exists (service-role). */
export async function signalExists(id: string): Promise<boolean | null> {
  const cfg = config();
  if (!cfg) return null;
  try {
    const response = await fetch(
      `${cfg.url}/rest/v1/signals?id=eq.${encodeURIComponent(id)}&select=id&limit=1`,
      { headers: headers(cfg.serviceKey), ...READ_CACHE },
    );
    if (!response.ok) return null;
    const rows = (await response.json()) as unknown[];
    return Array.isArray(rows) && rows.length > 0;
  } catch {
    return null;
  }
}

/** Upload a PNG to the public signal-charts bucket; return its public URL.
 * Mirrors signals/chart/upload.py (`suffix` → `{id}{suffix}.png`). */
export async function uploadSignalChartPng(
  signalId: string,
  png: Buffer,
  kind: "setup" | "outcome" = "setup",
): Promise<string | null> {
  const cfg = config();
  if (!cfg) return null;
  const suffix = kind === "outcome" ? "-outcome" : "";
  const path = `${signalId}${suffix}.png`;
  try {
    const response = await fetch(
      `${cfg.url}/storage/v1/object/${SIGNAL_CHART_BUCKET}/${path}`,
      {
        method: "POST",
        headers: {
          apikey: cfg.serviceKey,
          Authorization: `Bearer ${cfg.serviceKey}`,
          "Content-Type": "image/png",
          "x-upsert": "true",
        },
        body: new Uint8Array(png),
      },
    );
    if (!response.ok && response.status !== 200 && response.status !== 201) {
      return null;
    }
    return `${cfg.url}/storage/v1/object/public/${SIGNAL_CHART_BUCKET}/${path}`;
  } catch {
    return null;
  }
}

/** PATCH chart_url or outcome_chart_url on one signal row.
 * Returns previous chart URL (null if none) so callers can detect first upload. */
export async function setSignalChartUrl(
  signalId: string,
  url: string,
  kind: "setup" | "outcome" = "setup",
): Promise<{ ok: boolean; previousUrl: string | null }> {
  const cfg = config();
  if (!cfg) return { ok: false, previousUrl: null };
  const field = kind === "outcome" ? "outcome_chart_url" : "chart_url";
  let previousUrl: string | null = null;
  try {
    const before = await fetch(
      `${cfg.url}/rest/v1/signals?id=eq.${encodeURIComponent(signalId)}` +
        `&select=${field}`,
      { headers: headers(cfg.serviceKey), ...READ_CACHE },
    );
    if (before.ok) {
      const rows = (await before.json()) as Array<Record<string, string | null>>;
      const prev = rows[0]?.[field];
      previousUrl = typeof prev === "string" ? prev : null;
    }
    const response = await fetch(
      `${cfg.url}/rest/v1/signals?id=eq.${encodeURIComponent(signalId)}`,
      {
        method: "PATCH",
        headers: { ...headers(cfg.serviceKey), Prefer: "return=minimal" },
        body: JSON.stringify({ [field]: url }),
      },
    );
    return {
      ok: response.ok || response.status === 204,
      previousUrl,
    };
  } catch {
    return { ok: false, previousUrl };
  }
}

export type SignalAlertRow = {
  id: string;
  symbol: string;
  timeframe: string;
  direction: string;
  entry: number;
  stop_loss: number;
  take_profit: number;
  take_profit_1: number | null;
  take_profit_2: number | null;
  take_profit_3: number | null;
  confidence: number;
  rationale: string;
  chart_url: string | null;
};

export async function getSignalAlertRow(
  id: string,
): Promise<SignalAlertRow | null> {
  const cfg = config();
  if (!cfg) return null;
  try {
    const response = await fetch(
      `${cfg.url}/rest/v1/signals?id=eq.${encodeURIComponent(id)}` +
        `&select=id,symbol,timeframe,direction,entry,stop_loss,take_profit,` +
        `take_profit_1,take_profit_2,take_profit_3,confidence,rationale,chart_url` +
        `&limit=1`,
      { headers: headers(cfg.serviceKey), ...READ_CACHE },
    );
    if (!response.ok) return null;
    const rows = (await response.json()) as SignalAlertRow[];
    return Array.isArray(rows) && rows.length > 0 ? rows[0] : null;
  } catch {
    return null;
  }
}

/** Python gold scalp/swing/war-room rows waiting for an MT5 ChartScreenShot.
 * BBMA is excluded — that EA uploads immediately after publish. */
export type PendingSetupChart = {
  id: string;
  symbol: string;
  timeframe: string;
  direction: string;
  entry: number;
  stop_loss: number;
  take_profit: number;
  take_profit_2: number | null;
  take_profit_3: number | null;
  indicators: Record<string, unknown> | null;
  created_at: string;
};

const PENDING_CHART_TFS = ["1m", "5m", "15m", "1h", "floor"] as const;
const PENDING_CHART_MAX_AGE_HOURS = 48;

export async function listPendingSetupCharts(
  symbol: string,
  opts: { timeframe?: string; limit?: number } = {},
): Promise<PendingSetupChart[] | null> {
  const cfg = config();
  if (!cfg) return null;
  const canon = symbol.trim().toUpperCase();
  if (!canon) return null;
  const limit = Math.min(Math.max(opts.limit ?? 5, 1), 20);
  const since = new Date(
    Date.now() - PENDING_CHART_MAX_AGE_HOURS * 60 * 60 * 1000,
  ).toISOString();

  let tfFilter = `timeframe=in.(${PENDING_CHART_TFS.join(",")})`;
  if (opts.timeframe) {
    const tf = opts.timeframe.trim().toLowerCase();
    if (!(PENDING_CHART_TFS as readonly string[]).includes(tf)) return [];
    tfFilter = `timeframe=eq.${encodeURIComponent(tf)}`;
  }

  try {
    const response = await fetch(
      `${cfg.url}/rest/v1/signals?symbol=eq.${encodeURIComponent(canon)}` +
        `&chart_url=is.null&shadow=is.false&closed_at=is.null` +
        `&status=in.(open,tp1_hit,tp2_hit)` +
        `&created_at=gte.${encodeURIComponent(since)}` +
        `&${tfFilter}` +
        `&select=id,symbol,timeframe,direction,entry,stop_loss,take_profit,` +
        `take_profit_2,take_profit_3,indicators,created_at` +
        `&order=created_at.asc&limit=${limit}`,
      { headers: headers(cfg.serviceKey), ...READ_CACHE },
    );
    if (!response.ok) return null;
    const rows = (await response.json()) as PendingSetupChart[];
    return Array.isArray(rows) ? rows : [];
  } catch {
    return null;
  }
}

const TOOLS_BUCKET = "tools";

export type ToolInsert = {
  id: string;
  title_km: string;
  description_km: string;
  category: string;
  file_url: string | null;
  file_name: string | null;
  mime_type: string | null;
  file_size: number | null;
  external_url: string | null;
  sort_order: number;
  published: boolean;
};

type ToolRow = {
  id: string;
  title_km: string;
  description_km: string;
  category: string;
  file_url: string | null;
  file_name: string | null;
  mime_type: string | null;
  file_size: number | null;
  external_url: string | null;
  sort_order: number;
  published: boolean;
  created_at: string;
  updated_at: string;
};

const TOOL_SELECT =
  "id,title_km,description_km,category,file_url,file_name,mime_type,file_size,external_url,sort_order,published,created_at,updated_at";

/** All tools for admin (includes unpublished). */
export async function listAllTools(): Promise<ToolRow[]> {
  const cfg = config();
  if (!cfg) return [];
  try {
    const response = await fetch(
      `${cfg.url}/rest/v1/tools?select=${TOOL_SELECT}` +
        "&order=sort_order.asc,created_at.desc",
      { headers: headers(cfg.serviceKey), ...READ_CACHE },
    );
    if (!response.ok) return [];
    const rows = (await response.json()) as ToolRow[];
    return Array.isArray(rows) ? rows : [];
  } catch {
    return [];
  }
}

export async function getToolById(id: string): Promise<ToolRow | null> {
  const cfg = config();
  if (!cfg) return null;
  try {
    const response = await fetch(
      `${cfg.url}/rest/v1/tools?id=eq.${encodeURIComponent(id)}&select=${TOOL_SELECT}&limit=1`,
      { headers: headers(cfg.serviceKey), ...READ_CACHE },
    );
    if (!response.ok) return null;
    const rows = (await response.json()) as ToolRow[];
    return Array.isArray(rows) && rows.length > 0 ? rows[0] : null;
  } catch {
    return null;
  }
}

export async function insertTool(row: ToolInsert): Promise<boolean> {
  const cfg = config();
  if (!cfg) return false;
  const now = new Date().toISOString();
  try {
    const response = await fetch(`${cfg.url}/rest/v1/tools`, {
      method: "POST",
      headers: { ...headers(cfg.serviceKey), Prefer: "return=minimal" },
      body: JSON.stringify({ ...row, created_at: now, updated_at: now }),
    });
    return response.ok || response.status === 201;
  } catch {
    return false;
  }
}

export async function updateToolPublished(
  id: string,
  published: boolean,
): Promise<boolean> {
  const cfg = config();
  if (!cfg) return false;
  try {
    const response = await fetch(
      `${cfg.url}/rest/v1/tools?id=eq.${encodeURIComponent(id)}`,
      {
        method: "PATCH",
        headers: { ...headers(cfg.serviceKey), Prefer: "return=minimal" },
        body: JSON.stringify({
          published,
          updated_at: new Date().toISOString(),
        }),
      },
    );
    return response.ok || response.status === 204;
  } catch {
    return false;
  }
}

export async function deleteToolRow(id: string): Promise<boolean> {
  const cfg = config();
  if (!cfg) return false;
  try {
    const response = await fetch(
      `${cfg.url}/rest/v1/tools?id=eq.${encodeURIComponent(id)}`,
      {
        method: "DELETE",
        headers: headers(cfg.serviceKey),
      },
    );
    return response.ok || response.status === 204;
  } catch {
    return false;
  }
}

/** Upload a tool file to the public tools bucket. */
export async function uploadToolFile(
  toolId: string,
  fileName: string,
  bytes: Buffer,
  mimeType: string,
): Promise<string | null> {
  const cfg = config();
  if (!cfg) return null;
  const safeName = fileName.replace(/[^a-zA-Z0-9._-]/g, "_").slice(0, 120);
  const path = `${toolId}/${safeName || "download"}`;
  try {
    const response = await fetch(
      `${cfg.url}/storage/v1/object/${TOOLS_BUCKET}/${path}`,
      {
        method: "POST",
        headers: {
          apikey: cfg.serviceKey,
          Authorization: `Bearer ${cfg.serviceKey}`,
          "Content-Type": mimeType || "application/octet-stream",
          "x-upsert": "true",
        },
        body: new Uint8Array(bytes),
      },
    );
    if (!response.ok && response.status !== 200 && response.status !== 201) {
      return null;
    }
    return `${cfg.url}/storage/v1/object/public/${TOOLS_BUCKET}/${path}`;
  } catch {
    return null;
  }
}

/** Best-effort delete of a stored tool file from its public URL. */
export async function deleteToolStorageObject(fileUrl: string): Promise<void> {
  const cfg = config();
  if (!cfg || !fileUrl.includes(`/${TOOLS_BUCKET}/`)) return;
  const marker = `/object/public/${TOOLS_BUCKET}/`;
  const idx = fileUrl.indexOf(marker);
  if (idx < 0) return;
  const path = fileUrl.slice(idx + marker.length);
  if (!path) return;
  try {
    await fetch(`${cfg.url}/storage/v1/object/${TOOLS_BUCKET}/${path}`, {
      method: "DELETE",
      headers: headers(cfg.serviceKey),
    });
  } catch {
    // soft-fail
  }
}

/** TS mirror of signals/storage.py:update_signal_outcome's conditional-claim
 * mode: PATCH only applies if the row is still in `expectedStatus`, so the
 * slow Python cron and this instant path can't both win the same event. */
export async function updateSignalOutcomeClaim(
  id: string,
  status: string,
  at: string,
  opts: { terminal: boolean; expectedStatus: string },
): Promise<boolean> {
  const cfg = config();
  if (!cfg) return false;

  const payload: Record<string, string> = { status };
  let terminal = opts.terminal;
  if (status === "tp1_hit" && !terminal) {
    payload.tp1_hit_at = at;
  } else if (status === "tp2_hit" && !terminal) {
    payload.tp2_hit_at = at;
  } else if (status === "tp3_hit" || status === "tp_hit") {
    payload.tp3_hit_at = at;
    terminal = true;
  }
  if (terminal) payload.closed_at = at;

  const response = await fetch(
    `${cfg.url}/rest/v1/signals?id=eq.${id}&status=eq.${opts.expectedStatus}`,
    {
      method: "PATCH",
      headers: { ...headers(cfg.serviceKey), Prefer: "return=representation" },
      body: JSON.stringify(payload),
    },
  );
  if (!response.ok) {
    throw new Error(`${response.status} Supabase PATCH failed`);
  }
  const rows = (await response.json()) as unknown[];
  return Array.isArray(rows) && rows.length > 0;
}
