import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { getDebateForSignal, getDebates } from "@/lib/debates";

const ROW = {
  id: "debate-1",
  signal_id: "sig-1",
  symbol: "BTCUSD",
  timeframe: "1h",
  direction: "long",
  transcript: [
    { agent: "Structure Analyst", avatar: "S", message: "Sweep + CHoCH clean." },
    { agent: "Momentum Analyst", avatar: "M", message: "RSI supportive." },
    { agent: "Manager", avatar: "Mgr", message: "Take the long." },
  ],
  manager_verdict: "agree",
  manager_confidence: 78,
  created_at: "2026-08-01T00:00:00+00:00",
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

describe("getDebates", () => {
  it("maps rows and keeps signalId", async () => {
    mockFetch([ROW]);
    const debates = await getDebates(3);
    expect(debates).toHaveLength(1);
    expect(debates[0].signalId).toBe("sig-1");
    expect(debates[0].managerVerdict).toBe("agree");
  });
});

describe("getDebateForSignal", () => {
  it("queries by signal_id", async () => {
    const fetchFn = mockFetch([ROW]);
    const debate = await getDebateForSignal("sig-1");
    expect(debate?.id).toBe("debate-1");
    expect(debate?.transcript).toHaveLength(3);
    const url = String(fetchFn.mock.calls[0][0]);
    expect(url).toContain("signal_id=eq.sig-1");
    expect(url).toContain("limit=1");
  });

  it("returns null when no debate exists", async () => {
    mockFetch([]);
    expect(await getDebateForSignal("missing")).toBeNull();
  });
});
