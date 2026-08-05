import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  getOpenSignalsForSymbol,
  invalidateOpenSignalsCache,
  updateSignalOutcomeClaim,
} from "@/lib/supabase/admin";

beforeEach(() => {
  process.env.NEXT_PUBLIC_SUPABASE_URL = "https://abc.supabase.co";
  process.env.SUPABASE_SERVICE_ROLE_KEY = "service-key";
});

afterEach(() => {
  vi.unstubAllGlobals();
  delete process.env.NEXT_PUBLIC_SUPABASE_URL;
  delete process.env.SUPABASE_SERVICE_ROLE_KEY;
  // getOpenSignalsForSymbol caches per-symbol at module scope -- every test
  // in this file uses "XAUUSD", so a stale cache would leak between tests.
  invalidateOpenSignalsCache("XAUUSD");
});

describe("getOpenSignalsForSymbol", () => {
  it("queries open/tp1/tp2 rows for the given symbol, shadow rows included", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => [{ id: "sig-1", symbol: "XAUUSD" }],
    });
    vi.stubGlobal("fetch", fetchMock);

    const rows = await getOpenSignalsForSymbol("XAUUSD");

    expect(rows).toEqual([{ id: "sig-1", symbol: "XAUUSD" }]);
    const [url] = fetchMock.mock.calls[0];
    expect(url).toContain("symbol=eq.XAUUSD");
    expect(url).toContain("status=in.(open,tp1_hit,tp2_hit)");
    expect(url).toContain("closed_at=is.null");
    expect(url).not.toContain("shadow=is.false"); // parity with list_open_signals
  });

  it("returns null when the request fails", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false }));
    expect(await getOpenSignalsForSymbol("XAUUSD")).toBeNull();
  });

  it("serves a repeat call for the same symbol from cache, without refetching", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => [{ id: "sig-1", symbol: "XAUUSD" }],
    });
    vi.stubGlobal("fetch", fetchMock);

    await getOpenSignalsForSymbol("XAUUSD");
    await getOpenSignalsForSymbol("XAUUSD");

    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("refetches after invalidateOpenSignalsCache", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => [{ id: "sig-1", symbol: "XAUUSD" }],
    });
    vi.stubGlobal("fetch", fetchMock);

    await getOpenSignalsForSymbol("XAUUSD");
    invalidateOpenSignalsCache("XAUUSD");
    await getOpenSignalsForSymbol("XAUUSD");

    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});

describe("updateSignalOutcomeClaim", () => {
  it("claims successfully when the conditional PATCH matches a row", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => [{ id: "sig-1" }],
    });
    vi.stubGlobal("fetch", fetchMock);

    const claimed = await updateSignalOutcomeClaim(
      "sig-1", "sl_hit", "2026-08-04T12:00:00Z",
      { terminal: true, expectedStatus: "open" },
    );

    expect(claimed).toBe(true);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toContain("id=eq.sig-1");
    expect(url).toContain("status=eq.open");
    expect(init.method).toBe("PATCH");
    expect(init.headers.Prefer).toBe("return=representation");
    const body = JSON.parse(init.body);
    expect(body).toEqual({ status: "sl_hit", closed_at: "2026-08-04T12:00:00Z" });
  });

  it("returns false when another writer already claimed the row", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => [] }));

    const claimed = await updateSignalOutcomeClaim(
      "sig-1", "sl_hit", "2026-08-04T12:00:00Z",
      { terminal: true, expectedStatus: "open" },
    );

    expect(claimed).toBe(false);
  });

  it("stamps tp1_hit_at instead of closed_at for a non-terminal TP1 claim", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => [{ id: "sig-1" }] });
    vi.stubGlobal("fetch", fetchMock);

    await updateSignalOutcomeClaim(
      "sig-1", "tp1_hit", "2026-08-04T12:00:00Z",
      { terminal: false, expectedStatus: "open" },
    );

    const body = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(body).toEqual({ status: "tp1_hit", tp1_hit_at: "2026-08-04T12:00:00Z" });
  });
});

describe("upsertMt5LastTick", () => {
  it("upserts bid/ask/mid to mt5_last_ticks when table exists", async () => {
    const { upsertMt5LastTick } = await import("@/lib/supabase/admin");
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 201 });
    vi.stubGlobal("fetch", fetchMock);

    const ok = await upsertMt5LastTick(
      "XAUUSD",
      { bid: 4120.0, ask: 4120.4, mid: 4120.2 },
      1722825600,
    );

    expect(ok).toBe(true);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toContain("/mt5_last_ticks");
    expect(init.method).toBe("POST");
    expect(init.headers.Prefer).toContain("merge-duplicates");
    const body = JSON.parse(init.body as string);
    expect(body.symbol).toBe("XAUUSD");
    expect(body.bid).toBe(4120.0);
    expect(body.ask).toBe(4120.4);
    expect(body.mid).toBe(4120.2);
    expect(body.price).toBe(4120.2);
    expect(body.tick_time).toBe(new Date(1722825600 * 1000).toISOString());
  });

  it("falls back to Storage when the table is missing", async () => {
    const { upsertMt5LastTick } = await import("@/lib/supabase/admin");
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: false,
        status: 404,
        json: async () => ({ code: "PGRST205" }),
      })
      .mockResolvedValueOnce({ ok: true, status: 200 });
    vi.stubGlobal("fetch", fetchMock);

    const ok = await upsertMt5LastTick("XAUUSD", { bid: 4120.5, ask: 4120.7 }, 1722825600);

    expect(ok).toBe(true);
    expect(fetchMock.mock.calls[1][0]).toContain(
      "/storage/v1/object/signal-charts/mt5-last-ticks/XAUUSD.json",
    );
  });
});
