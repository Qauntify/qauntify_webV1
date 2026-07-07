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
