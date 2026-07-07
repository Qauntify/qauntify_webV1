// Server-only admin helpers: service-role calls to Supabase Auth admin API
// and the bot_settings table. Import only from server components/actions —
// SUPABASE_SERVICE_ROLE_KEY must never reach the browser.

export type AdminUser = {
  id: string;
  email: string;
  createdAt: string;
  lastSignInAt: string | null;
};

export type BotSettings = {
  symbols: string[];
  minAlertConfidence: number;
};

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

export function isAdminEmail(email: string | null | undefined): boolean {
  if (!email) return false;
  const admins = (process.env.ADMIN_EMAILS ?? "")
    .split(",")
    .map((e) => e.trim().toLowerCase())
    .filter(Boolean);
  return admins.includes(email.toLowerCase());
}

export async function listUsers(): Promise<AdminUser[] | null> {
  const cfg = config();
  if (!cfg) return null;
  try {
    const response = await fetch(
      `${cfg.url}/auth/v1/admin/users?per_page=200`,
      { headers: headers(cfg.serviceKey), cache: "no-store" },
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
      cache: "no-store",
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
      `${cfg.url}/rest/v1/bot_settings?id=eq.1&select=symbols,min_alert_confidence`,
      { headers: headers(cfg.serviceKey), cache: "no-store" },
    );
    if (!response.ok) return null;
    const rows = await response.json();
    const row = Array.isArray(rows) ? rows[0] : null;
    if (!row || !Array.isArray(row.symbols)) return null;
    return {
      symbols: row.symbols,
      minAlertConfidence: row.min_alert_confidence,
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
        updated_at: new Date().toISOString(),
      }),
    });
    return response.ok;
  } catch {
    return false;
  }
}

export async function listAiEvents(limit = 50): Promise<AiEvent[] | null> {
  const cfg = config();
  if (!cfg) return null;
  try {
    const response = await fetch(
      `${cfg.url}/rest/v1/ai_events?select=*` +
        `&order=created_at.desc&limit=${encodeURIComponent(String(limit))}`,
      { headers: headers(cfg.serviceKey), cache: "no-store" },
    );
    if (!response.ok) return null;
    const rows = (await response.json()) as AiEventRow[];
    if (!Array.isArray(rows)) return null;
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
  } catch {
    return null;
  }
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

export async function latestEngineRun(): Promise<EngineRun | null> {
  const cfg = config();
  if (!cfg) return null;
  try {
    const response = await fetch(
      `${cfg.url}/rest/v1/engine_runs?select=*` +
        `&order=finished_at.desc&limit=1`,
      { headers: headers(cfg.serviceKey), cache: "no-store" },
    );
    if (!response.ok) return null;
    const rows = (await response.json()) as EngineRunRow[];
    const row = Array.isArray(rows) ? rows[0] : null;
    if (!row) return null;
    return {
      id: String(row.id),
      runId: String(row.run_id),
      timeframe: String(row.timeframe),
      storedCount: Number(row.stored_count ?? 0),
      outcomes: row.outcomes,
      finishedAt: String(row.finished_at),
    };
  } catch {
    return null;
  }
}

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
      cache: "no-store",
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
