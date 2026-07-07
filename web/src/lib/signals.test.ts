import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { getSignals, getStats } from "./signals";

const ROW = {
  id: "abc-123",
  symbol: "BTCUSDT",
  timeframe: "1h",
  direction: "long",
  entry: 108240.0,
  stop_loss: 106900.0,
  take_profit: 110920.0,
  confidence: 82,
  rationale: "Momentum aligns with news.",
  indicators: { ema9: 108100, ema21: 107900, rsi: 55.2, macd_hist: 12.4 },
  news_headlines: ["ETF inflows surge"],
  created_at: "2026-07-06T09:00:00+00:00",
};

function mockFetch(payload: unknown, ok = true) {
  const fn = vi.fn().mockResolvedValue({
    ok,
    json: () => Promise.resolve(payload),
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

beforeEach(() => {
  process.env.NEXT_PUBLIC_SUPABASE_URL = "https://abc.supabase.co";
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = "anon-key";
});

afterEach(() => {
  vi.unstubAllGlobals();
  delete process.env.NEXT_PUBLIC_SUPABASE_URL;
  delete process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
});

describe("getSignals", () => {
  it("returns [] when Supabase env vars are missing", async () => {
    delete process.env.NEXT_PUBLIC_SUPABASE_URL;
    const fetchFn = mockFetch([ROW]);
    expect(await getSignals()).toEqual([]);
    expect(fetchFn).not.toHaveBeenCalled();
  });

  it("maps PostgREST rows to camelCase signals", async () => {
    mockFetch([ROW]);
    const signals = await getSignals();
    expect(signals).toHaveLength(1);
    const s = signals[0];
    expect(s.id).toBe("abc-123");
    expect(s.direction).toBe("long");
    expect(s.stopLoss).toBe(106900.0);
    expect(s.takeProfit).toBe(110920.0);
    expect(s.indicators.macdHist).toBe(12.4);
    expect(s.newsHeadlines).toEqual(["ETF inflows surge"]);
  });

  it("requests newest-first with the limit and anon auth headers", async () => {
    const fetchFn = mockFetch([]);
    await getSignals(5);
    const [url, options] = fetchFn.mock.calls[0];
    expect(url).toBe(
      "https://abc.supabase.co/rest/v1/signals?select=*&order=created_at.desc&limit=5",
    );
    expect(options.headers.apikey).toBe("anon-key");
    expect(options.headers.Authorization).toBe("Bearer anon-key");
    expect(options.cache).toBe("no-store");
  });

  it("skips malformed rows instead of crashing", async () => {
    mockFetch([{ ...ROW, direction: "sideways" }, ROW]);
    expect(await getSignals()).toHaveLength(1);
  });

  it("returns [] on HTTP errors", async () => {
    mockFetch({ message: "unauthorized" }, false);
    expect(await getSignals()).toEqual([]);
  });

  it("returns [] when fetch itself rejects", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("network down")));
    expect(await getSignals()).toEqual([]);
  });
});

describe("getStats", () => {
  it("returns zeros when Supabase env vars are missing", async () => {
    delete process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
    expect(await getStats()).toEqual({
      total: 0,
      avgConfidence: 0,
      longs: 0,
      shorts: 0,
      tpHits: 0,
      slHits: 0,
      winRate: null,
    });
  });

  it("computes totals, rounded average confidence, and direction split", async () => {
    mockFetch([
      { confidence: 80, direction: "long", status: "tp_hit" },
      { confidence: 71, direction: "short", status: "sl_hit" },
      { confidence: 90, direction: "long" },
    ]);
    expect(await getStats()).toEqual({
      total: 3,
      avgConfidence: 80,
      longs: 2,
      shorts: 1,
      tpHits: 1,
      slHits: 1,
      winRate: 50,
    });
  });
});
