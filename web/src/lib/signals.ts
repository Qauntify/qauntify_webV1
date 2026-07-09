export type SignalStatus = "open" | "tp_hit" | "sl_hit" | "expired";

export type Signal = {
  id: string;
  symbol: string;
  timeframe: string;
  direction: "long" | "short";
  entry: number;
  stopLoss: number;
  takeProfit: number;
  confidence: number;
  rationale: string;
  indicators: { ema9: number; ema21: number; rsi: number; macdHist: number };
  newsHeadlines: string[];
  createdAt: string;
  status: SignalStatus;
};

export type Stats = {
  total: number;
  avgConfidence: number;
  longs: number;
  shorts: number;
  tpHits: number;
  slHits: number;
  // Percent of closed signals that hit TP; null until something closes.
  winRate: number | null;
};

type SignalRow = {
  id: string;
  symbol: string;
  timeframe: string;
  direction: string;
  entry: number;
  stop_loss: number;
  take_profit: number;
  confidence: number;
  rationale: string;
  indicators: { ema9: number; ema21: number; rsi: number; macd_hist: number };
  news_headlines: unknown;
  created_at: string;
  // Absent until supabase/schema.sql adds the column; treated as "open".
  status?: string;
};

function parseStatus(value: string | undefined): SignalStatus {
  if (value === "tp_hit" || value === "sl_hit" || value === "expired") {
    return value;
  }
  return "open";
}

function supabaseConfig(): { url: string; anonKey: string } | null {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !anonKey) return null;
  return { url: url.replace(/\/$/, ""), anonKey };
}

async function fetchRows(
  query: string,
  accessToken?: string,
): Promise<SignalRow[] | null> {
  const config = supabaseConfig();
  if (!config) return null;
  try {
    const response = await fetch(
      `${config.url}/rest/v1/signals?${query}`,
      {
        headers: {
          apikey: config.anonKey,
          // A signed-in user's JWT makes RLS grant full history;
          // the anon key alone only sees the 24-hour preview.
          Authorization: `Bearer ${accessToken ?? config.anonKey}`,
        },
        cache: "no-store", // signals change whenever the engine runs
      },
    );
    if (!response.ok) return null;
    const rows = await response.json();
    return Array.isArray(rows) ? rows : null;
  } catch {
    return null;
  }
}

async function callRpc<T>(
  fn: string,
  params: Record<string, unknown>,
  accessToken?: string,
): Promise<T | null> {
  const config = supabaseConfig();
  if (!config) return null;
  try {
    const response = await fetch(`${config.url}/rest/v1/rpc/${fn}`, {
      method: "POST",
      headers: {
        apikey: config.anonKey,
        // A signed-in user's JWT makes RLS grant full history;
        // the anon key alone only sees the 24-hour preview.
        Authorization: `Bearer ${accessToken ?? config.anonKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(params),
      cache: "no-store", // signals change whenever the engine runs
    });
    if (!response.ok) return null;
    return (await response.json()) as T;
  } catch {
    return null;
  }
}

async function fetchRowsPaginated(
  query: string,
  page: number,
  pageSize: number,
  accessToken?: string,
): Promise<{ rows: SignalRow[]; total: number } | null> {
  const config = supabaseConfig();
  if (!config) return null;
  const offset = (page - 1) * pageSize;
  const rangeEnd = offset + pageSize - 1;
  try {
    const response = await fetch(
      `${config.url}/rest/v1/signals?${query}`,
      {
        headers: {
          apikey: config.anonKey,
          Authorization: `Bearer ${accessToken ?? config.anonKey}`,
          Range: `${offset}-${rangeEnd}`,
          Prefer: "count=exact",
        },
        cache: "no-store",
      },
    );
    if (!response.ok) return null;
    const rows = (await response.json()) as SignalRow[];
    const contentRange = response.headers.get("content-range");
    const match = contentRange?.match(/\d+-\d+\/(\d+|\*)/);
    const total = match && match[1] !== "*" ? Number(match[1]) : rows.length;
    return { rows: Array.isArray(rows) ? rows : [], total };
  } catch {
    return null;
  }
}

function parseRow(row: SignalRow): Signal | null {
  if (row.direction !== "long" && row.direction !== "short") return null;
  if (!Array.isArray(row.news_headlines)) return null;
  if (typeof row.indicators !== "object" || row.indicators === null) return null;
  return {
    id: row.id,
    symbol: row.symbol,
    timeframe: row.timeframe,
    direction: row.direction,
    entry: row.entry,
    stopLoss: row.stop_loss,
    takeProfit: row.take_profit,
    confidence: row.confidence,
    rationale: row.rationale,
    indicators: {
      ema9: row.indicators.ema9,
      ema21: row.indicators.ema21,
      rsi: row.indicators.rsi,
      macdHist: row.indicators.macd_hist,
    },
    newsHeadlines: row.news_headlines as string[],
    createdAt: row.created_at,
    status: parseStatus(row.status),
  };
}

export async function getSignals(
  limit = 50,
  accessToken?: string,
  timeframe?: string,
): Promise<Signal[]> {
  const timeframeFilter = timeframe ? `&timeframe=eq.${timeframe}` : "";
  const rows = await fetchRows(
    `select=*${timeframeFilter}&order=created_at.desc&limit=${limit}`,
    accessToken,
  );
  if (!rows) return [];
  return rows.map(parseRow).filter((s): s is Signal => s !== null);
}

const ZERO_STATS: Stats = {
  total: 0, avgConfidence: 0, longs: 0, shorts: 0,
  tpHits: 0, slHits: 0, winRate: null,
};

type StatsRpcRow = {
  total: number;
  avg_confidence: number;
  longs: number;
  shorts: number;
  tp_hits: number;
  sl_hits: number;
};

export async function getStats(
  accessToken?: string,
  timeframe?: string,
): Promise<Stats> {
  // Aggregated server-side by supabase/schema.sql's get_signal_stats() —
  // counting/averaging in Postgres instead of pulling every matching row
  // into Node. Degrades to zero stats (not a crash) if the RPC 404s, e.g.
  // the migration hasn't been applied to this project yet.
  const row = await callRpc<StatsRpcRow[]>(
    "get_signal_stats",
    { p_timeframe: timeframe ?? null },
    accessToken,
  ).then((rows) => rows?.[0]);
  if (!row) return ZERO_STATS;
  const closed = row.tp_hits + row.sl_hits;
  return {
    total: row.total,
    avgConfidence: row.avg_confidence,
    longs: row.longs,
    shorts: row.shorts,
    tpHits: row.tp_hits,
    slHits: row.sl_hits,
    winRate: closed > 0 ? Math.round((row.tp_hits / closed) * 100) : null,
  };
}

export const SIGNALS_PAGE_SIZE = 12;

export type SignalsPage = {
  signals: Signal[];
  page: number;
  pageSize: number;
  total: number;
  totalPages: number;
};

export async function getSignalsPaginated(
  page = 1,
  accessToken?: string,
  timeframe?: string,
  pageSize = SIGNALS_PAGE_SIZE,
): Promise<SignalsPage> {
  const safePage = Number.isInteger(page) && page > 0 ? page : 1;
  const timeframeFilter = timeframe ? `&timeframe=eq.${timeframe}` : "";
  const query = `select=*${timeframeFilter}&order=created_at.desc`;

  const result = await fetchRowsPaginated(query, safePage, pageSize, accessToken);
  if (!result) {
    return { signals: [], page: 1, pageSize, total: 0, totalPages: 1 };
  }

  const signals = result.rows.map(parseRow).filter((s): s is Signal => s !== null);
  const totalPages = Math.max(1, Math.ceil(result.total / pageSize));
  return {
    signals,
    page: Math.min(safePage, totalPages),
    pageSize,
    total: result.total,
    totalPages,
  };
}

export type DailyPnL = {
  date: string; // YYYY-MM-DD
  wins: number;
  losses: number;
  net: number; // wins - losses
};

export async function getDailyPnLStats(
  accessToken?: string,
  days = 365
): Promise<DailyPnL[]> {
  // Fetch all signals in the last N days
  const cutoff = new Date();
  cutoff.setDate(cutoff.getDate() - days);
  
  const query = `select=created_at,status&created_at=gte.${cutoff.toISOString()}&order=created_at.desc`;
  const rows = await fetchRows(query, accessToken);
  
  if (!rows || rows.length === 0) return [];

  const dailyMap = new Map<string, { wins: number; losses: number }>();

  for (const r of rows) {
    const status = parseStatus(r.status);
    if (status !== "tp_hit" && status !== "sl_hit") continue;
    
    // Get YYYY-MM-DD
    const dateStr = new Date(r.created_at).toISOString().split("T")[0];
    
    if (!dailyMap.has(dateStr)) {
      dailyMap.set(dateStr, { wins: 0, losses: 0 });
    }
    
    const stats = dailyMap.get(dateStr)!;
    if (status === "tp_hit") stats.wins++;
    if (status === "sl_hit") stats.losses++;
  }

  const result: DailyPnL[] = [];
  for (const [date, stats] of dailyMap.entries()) {
    result.push({
      date,
      wins: stats.wins,
      losses: stats.losses,
      net: stats.wins - stats.losses,
    });
  }

  // Sort by date ascending (oldest to newest)
  return result.sort((a, b) => a.date.localeCompare(b.date));
}
