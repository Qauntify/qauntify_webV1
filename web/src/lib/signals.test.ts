import Database from "better-sqlite3";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { getSignals, getStats } from "./signals";

const SCHEMA = `
CREATE TABLE IF NOT EXISTS signals (
    id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    direction TEXT NOT NULL,
    entry REAL NOT NULL,
    stop_loss REAL NOT NULL,
    take_profit REAL NOT NULL,
    confidence INTEGER NOT NULL,
    rationale TEXT NOT NULL,
    indicators TEXT NOT NULL,
    news_headlines TEXT NOT NULL,
    created_at TEXT NOT NULL
)`;

let dir: string;
let dbFile: string;

function insertSignal(
  db: Database.Database,
  overrides: Partial<Record<string, unknown>> = {},
) {
  const row = {
    id: crypto.randomUUID(),
    symbol: "BTCUSDT",
    timeframe: "1h",
    direction: "long",
    entry: 108240.0,
    stop_loss: 106900.0,
    take_profit: 110920.0,
    confidence: 82,
    rationale: "Momentum aligns with news.",
    indicators: JSON.stringify({ ema9: 108100, ema21: 107900, rsi: 55.2, macd_hist: 12.4 }),
    news_headlines: JSON.stringify(["ETF inflows surge"]),
    created_at: "2026-07-06T09:00:00+00:00",
    ...overrides,
  };
  db.prepare(
    `INSERT INTO signals VALUES (@id, @symbol, @timeframe, @direction, @entry,
     @stop_loss, @take_profit, @confidence, @rationale, @indicators,
     @news_headlines, @created_at)`,
  ).run(row);
  return row;
}

beforeEach(() => {
  dir = mkdtempSync(path.join(tmpdir(), "signals-test-"));
  dbFile = path.join(dir, "signals.db");
  process.env.SIGNALS_DB_PATH = dbFile;
});

afterEach(() => {
  delete process.env.SIGNALS_DB_PATH;
  rmSync(dir, { recursive: true, force: true });
});

describe("getSignals", () => {
  it("returns [] when the database file does not exist", () => {
    expect(getSignals()).toEqual([]);
  });

  it("maps engine rows to camelCase signals with parsed JSON fields", () => {
    const db = new Database(dbFile);
    db.exec(SCHEMA);
    const row = insertSignal(db);
    db.close();

    const signals = getSignals();
    expect(signals).toHaveLength(1);
    const s = signals[0];
    expect(s.id).toBe(row.id);
    expect(s.direction).toBe("long");
    expect(s.stopLoss).toBe(106900.0);
    expect(s.takeProfit).toBe(110920.0);
    expect(s.indicators.macdHist).toBe(12.4);
    expect(s.newsHeadlines).toEqual(["ETF inflows surge"]);
  });

  it("orders newest first and respects the limit", () => {
    const db = new Database(dbFile);
    db.exec(SCHEMA);
    insertSignal(db, { created_at: "2026-07-05T01:00:00+00:00", symbol: "OLD1" });
    insertSignal(db, { created_at: "2026-07-06T01:00:00+00:00", symbol: "NEW1" });
    insertSignal(db, { created_at: "2026-07-05T12:00:00+00:00", symbol: "MID1" });
    db.close();

    const signals = getSignals(2);
    expect(signals.map((s) => s.symbol)).toEqual(["NEW1", "MID1"]);
  });

  it("skips rows with malformed JSON instead of crashing", () => {
    const db = new Database(dbFile);
    db.exec(SCHEMA);
    insertSignal(db, { indicators: "{not json" });
    insertSignal(db, { created_at: "2026-07-06T02:00:00+00:00" });
    db.close();

    expect(getSignals()).toHaveLength(1);
  });
});

describe("getStats", () => {
  it("returns zeros when the database file does not exist", () => {
    expect(getStats()).toEqual({ total: 0, avgConfidence: 0, longs: 0, shorts: 0 });
  });

  it("computes totals, rounded average confidence, and direction split", () => {
    const db = new Database(dbFile);
    db.exec(SCHEMA);
    insertSignal(db, { confidence: 80, direction: "long" });
    insertSignal(db, { confidence: 71, direction: "short" });
    insertSignal(db, { confidence: 90, direction: "long" });
    db.close();

    expect(getStats()).toEqual({ total: 3, avgConfidence: 80, longs: 2, shorts: 1 });
  });
});
