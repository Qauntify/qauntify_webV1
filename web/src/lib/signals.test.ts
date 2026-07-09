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

  it("filters by timeframe when a session is requested", async () => {
    const fetchFn = mockFetch([]);
    await getSignals(10, undefined, "15m");
    const [url] = fetchFn.mock.calls[0];
    expect(url).toBe(
      "https://abc.supabase.co/rest/v1/signals?select=*&timeframe=eq.15m&order=created_at.desc&limit=10",
    );
  });

  it("omits the timeframe filter when no session is requested", async () => {
    const fetchFn = mockFetch([]);
    await getSignals(10);
    const [url] = fetchFn.mock.calls[0];
    expect(url).not.toContain("timeframe=eq.");
  });

  it("keeps the expired status instead of treating it as open", async () => {
    mockFetch([{ ...ROW, status: "expired" }]);
    const signals = await getSignals();
    expect(signals[0].status).toBe("expired");
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
  const ZERO_STATS = {
    total: 0, avgConfidence: 0, longs: 0, shorts: 0,
    tpHits: 0, slHits: 0, winRate: null,
  };

  function mockRpc(row: Record<string, unknown>) {
    return mockFetch([row]);
  }

  it("returns zeros when Supabase env vars are missing", async () => {
    delete process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
    const fetchFn = mockFetch([]);
    expect(await getStats()).toEqual(ZERO_STATS);
    expect(fetchFn).not.toHaveBeenCalled();
  });

  it("calls the get_signal_stats RPC and maps the aggregated row", async () => {
    const fetchFn = mockRpc({
      total: 3, avg_confidence: 80, longs: 2, shorts: 1, tp_hits: 1, sl_hits: 1,
    });

    expect(await getStats()).toEqual({
      total: 3, avgConfidence: 80, longs: 2, shorts: 1,
      tpHits: 1, slHits: 1, winRate: 50,
    });

    const [url, options] = fetchFn.mock.calls[0];
    expect(url).toBe("https://abc.supabase.co/rest/v1/rpc/get_signal_stats");
    expect(options.method).toBe("POST");
    expect(options.headers.apikey).toBe("anon-key");
    expect(JSON.parse(options.body)).toEqual({ p_timeframe: null });
  });

  it("passes the timeframe as an RPC parameter, not a query filter", async () => {
    const fetchFn = mockRpc({
      total: 0, avg_confidence: 0, longs: 0, shorts: 0, tp_hits: 0, sl_hits: 0,
    });
    await getStats(undefined, "1h");
    const [, options] = fetchFn.mock.calls[0];
    expect(JSON.parse(options.body)).toEqual({ p_timeframe: "1h" });
  });

  it("returns null win rate when nothing has closed yet", async () => {
    const stats = await (async () => {
      mockRpc({ total: 3, avg_confidence: 75, longs: 2, shorts: 1, tp_hits: 0, sl_hits: 0 });
      return getStats();
    })();
    expect(stats.winRate).toBeNull();
  });

  it("degrades to zero stats when the RPC is unavailable (e.g. migration not yet applied)", async () => {
    mockFetch({ message: "function get_signal_stats() does not exist" }, false);
    expect(await getStats()).toEqual(ZERO_STATS);
  });

  it("degrades to zero stats when fetch itself rejects", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("network down")));
    expect(await getStats()).toEqual(ZERO_STATS);
  });
});
