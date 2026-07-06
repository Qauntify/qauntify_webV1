import Database from "better-sqlite3";
import path from "node:path";

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
  indicators: string;
  news_headlines: string;
  created_at: string;
};

// The engine writes signals.db at the repo root; the web app lives in web/.
function dbPath(): string {
  return (
    process.env.SIGNALS_DB_PATH ?? path.join(process.cwd(), "..", "signals.db")
  );
}

// Read-only handle, or null when the engine hasn't produced a DB yet.
function openDb(): Database.Database | null {
  try {
    return new Database(dbPath(), { readonly: true, fileMustExist: true });
  } catch {
    return null;
  }
}

function parseRow(row: SignalRow): Signal | null {
  try {
    const indicators = JSON.parse(row.indicators);
    const newsHeadlines = JSON.parse(row.news_headlines);
    if (!Array.isArray(newsHeadlines)) return null;
    if (row.direction !== "long" && row.direction !== "short") return null;
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
        ema9: indicators.ema9,
        ema21: indicators.ema21,
        rsi: indicators.rsi,
        macdHist: indicators.macd_hist,
      },
      newsHeadlines,
      createdAt: row.created_at,
    };
  } catch {
    return null;
  }
}

export function getSignals(limit = 50): Signal[] {
  const db = openDb();
  if (!db) return [];
  try {
    const rows = db
      .prepare("SELECT * FROM signals ORDER BY created_at DESC LIMIT ?")
      .all(limit) as SignalRow[];
    return rows.map(parseRow).filter((s): s is Signal => s !== null);
  } catch {
    return [];
  } finally {
    db.close();
  }
}

export function getStats(): Stats {
  const db = openDb();
  const empty: Stats = { total: 0, avgConfidence: 0, longs: 0, shorts: 0 };
  if (!db) return empty;
  try {
    const row = db
      .prepare(
        `SELECT
           COUNT(*) AS total,
           COALESCE(AVG(confidence), 0) AS avg_confidence,
           COALESCE(SUM(direction = 'long'), 0) AS longs,
           COALESCE(SUM(direction = 'short'), 0) AS shorts
         FROM signals`,
      )
      .get() as {
      total: number;
      avg_confidence: number;
      longs: number;
      shorts: number;
    };
    return {
      total: row.total,
      avgConfidence: Math.round(row.avg_confidence),
      longs: row.longs,
      shorts: row.shorts,
    };
  } catch {
    return empty;
  } finally {
    db.close();
  }
}
