import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { getOpenSignalsForSymbol, updateSignalOutcomeClaim } from "@/lib/supabase/admin";

beforeEach(() => {
  process.env.NEXT_PUBLIC_SUPABASE_URL = "https://abc.supabase.co";
  process.env.SUPABASE_SERVICE_ROLE_KEY = "service-key";
});

afterEach(() => {
  vi.unstubAllGlobals();
  delete process.env.NEXT_PUBLIC_SUPABASE_URL;
  delete process.env.SUPABASE_SERVICE_ROLE_KEY;
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
