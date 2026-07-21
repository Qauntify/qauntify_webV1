import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  armFloorRun,
  beginCycle,
  disableFloorRun,
  endCycleProgress,
  incrementFloorCycle,
  readFloorRunState,
  recordFloorSignal,
  setFloorRunPhase,
} from "./run-control";

function jsonResponse(body: unknown, ok = true) {
  return { ok, status: ok ? 200 : 500, json: async () => body };
}

describe("floor run-control (Supabase-backed)", () => {
  beforeEach(() => {
    process.env.NEXT_PUBLIC_SUPABASE_URL = "https://example.supabase.co";
    process.env.SUPABASE_SERVICE_ROLE_KEY = "service-role-test-key";
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    delete process.env.NEXT_PUBLIC_SUPABASE_URL;
    delete process.env.SUPABASE_SERVICE_ROLE_KEY;
  });

  it("readFloorRunState maps the row to FloorRunStatus", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse([{
      id: 1,
      enabled: true,
      in_progress: false,
      run_id: "run-1",
      cycle: 3,
      phase: "technical",
      last_message: "Cycle 3: technical desk analyzing gold...",
      last_signal: null,
      updated_at: "2026-07-18T00:00:00.000Z",
    }]));
    vi.stubGlobal("fetch", fetchMock);

    const status = await readFloorRunState();
    expect(status).toEqual({
      running: true,
      runId: "run-1",
      cycle: 3,
      phase: "technical",
      lastMessage: "Cycle 3: technical desk analyzing gold...",
      lastSignal: null,
    });
  });

  it("armFloorRun returns true and arms the row when not already enabled", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse([{ id: 1 }]));
    vi.stubGlobal("fetch", fetchMock);

    const armed = await armFloorRun("run-2");
    expect(armed).toBe(true);

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toContain("enabled=eq.false");
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(init.body)).toMatchObject({
      enabled: true,
      run_id: "run-2",
      cycle: 0,
      phase: "macro",
    });
  });

  it("armFloorRun returns false when already enabled", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse([]));
    vi.stubGlobal("fetch", fetchMock);

    expect(await armFloorRun("run-3")).toBe(false);
  });

  it("disableFloorRun PATCHes enabled=false", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse([{ id: 1 }]));
    vi.stubGlobal("fetch", fetchMock);

    await disableFloorRun();
    const [, init] = fetchMock.mock.calls[0];
    expect(JSON.parse(init.body)).toMatchObject({ enabled: false });
  });

  it("beginCycle returns true and marks in_progress when enabled and free", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse([{ id: 1 }]));
    vi.stubGlobal("fetch", fetchMock);

    const started = await beginCycle();
    expect(started).toBe(true);

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toContain("enabled=eq.true");
    expect(url).toContain("in_progress=eq.false");
    expect(JSON.parse(init.body)).toMatchObject({ in_progress: true });
  });

  it("beginCycle returns false when already in progress or disabled", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse([]));
    vi.stubGlobal("fetch", fetchMock);

    expect(await beginCycle()).toBe(false);
  });

  it("endCycleProgress PATCHes in_progress=false", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse([{ id: 1 }]));
    vi.stubGlobal("fetch", fetchMock);

    await endCycleProgress();
    const [, init] = fetchMock.mock.calls[0];
    expect(JSON.parse(init.body)).toMatchObject({ in_progress: false });
  });

  it("incrementFloorCycle reads current cycle then PATCHes cycle+1", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse([{ id: 1, cycle: 4 }]))
      .mockResolvedValueOnce(jsonResponse([{ id: 1 }]));
    vi.stubGlobal("fetch", fetchMock);

    const cycle = await incrementFloorCycle();
    expect(cycle).toBe(5);

    const [, patchInit] = fetchMock.mock.calls[1];
    expect(JSON.parse(patchInit.body)).toMatchObject({ cycle: 5 });
  });

  it("setFloorRunPhase PATCHes phase and lastMessage", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse([{ id: 1 }]));
    vi.stubGlobal("fetch", fetchMock);

    await setFloorRunPhase("pm", "Cycle 5: PM deciding signal or pass...");
    const [, init] = fetchMock.mock.calls[0];
    expect(JSON.parse(init.body)).toMatchObject({
      phase: "pm",
      last_message: "Cycle 5: PM deciding signal or pass...",
    });
  });

  it("recordFloorSignal PATCHes last_signal", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse([{ id: 1 }]));
    vi.stubGlobal("fetch", fetchMock);

    const signal = {
      direction: "long" as const,
      entry: 2400,
      stopLoss: 2390,
      takeProfit: 2420,
      confidence: 72,
      body: "Breakout setup.",
      createdAt: "2026-07-18T00:00:00.000Z",
    };
    await recordFloorSignal(signal);

    const [, init] = fetchMock.mock.calls[0];
    expect(JSON.parse(init.body)).toMatchObject({ last_signal: signal });
  });

  it("throws when Supabase returns a non-2xx response", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({}, false));
    vi.stubGlobal("fetch", fetchMock);

    await expect(readFloorRunState()).rejects.toThrow("Could not read floor run state");
  });

  it("throws when the floor_run_state row is missing", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse([]));
    vi.stubGlobal("fetch", fetchMock);

    await expect(readFloorRunState()).rejects.toThrow("floor_run_state row is missing");
  });
});
