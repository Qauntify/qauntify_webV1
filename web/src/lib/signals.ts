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
};

export type Stats = {
  total: number;
  avgConfidence: number;
  longs: number;
  shorts: number;
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
};

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
  };
}

export async function getSignals(
  limit = 50,
  accessToken?: string,
): Promise<Signal[]> {
  const rows = await fetchRows(
    `select=*&order=created_at.desc&limit=${limit}`,
    accessToken,
  );
  if (!rows) return [];
  return rows.map(parseRow).filter((s): s is Signal => s !== null);
}

export async function getStats(accessToken?: string): Promise<Stats> {
  // Low volume: fetch the two columns we aggregate and compute here.
  const rows = await fetchRows("select=confidence,direction", accessToken);
  if (!rows || rows.length === 0) {
    return { total: 0, avgConfidence: 0, longs: 0, shorts: 0 };
  }
  const total = rows.length;
  const sum = rows.reduce((acc, r) => acc + r.confidence, 0);
  const longs = rows.filter((r) => r.direction === "long").length;
  return {
    total,
    avgConfidence: Math.round(sum / total),
    longs,
    shorts: total - longs,
  };
}
