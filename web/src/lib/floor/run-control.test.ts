import { afterEach, describe, expect, it } from "vitest";

import {
  beginFloorRun,
  endFloorRun,
  floorRunSnapshot,
  incrementFloorCycle,
  recordFloorSignal,
  requestFloorStop,
  resetFloorRunState,
  setFloorRunPhase,
  shouldStopFloorRun,
} from "./run-control";

afterEach(() => {
  resetFloorRunState();
});

describe("floor run control", () => {
  it("tracks running state, cycles, and stop requests", () => {
    expect(beginFloorRun("run-1")).toBe(true);
    expect(floorRunSnapshot()).toMatchObject({
      running: true,
      runId: "run-1",
      cycle: 0,
      phase: "macro",
    });
    expect(beginFloorRun("run-2")).toBe(false);

    setFloorRunPhase("technical", "Scanning...");
    expect(floorRunSnapshot().phase).toBe("technical");
    expect(floorRunSnapshot().lastMessage).toBe("Scanning...");

    expect(incrementFloorCycle()).toBe(1);
    recordFloorSignal({
      direction: "long",
      entry: 2400,
      stopLoss: 2390,
      takeProfit: 2420,
      confidence: 72,
      body: "Breakout setup.",
      createdAt: "2026-07-17T12:00:00.000Z",
    });
    expect(floorRunSnapshot().lastSignal?.direction).toBe("long");

    requestFloorStop();
    expect(shouldStopFloorRun()).toBe(true);

    endFloorRun();
    expect(floorRunSnapshot().running).toBe(false);
    expect(floorRunSnapshot().lastSignal?.direction).toBe("long");
    expect(shouldStopFloorRun()).toBe(false);
  });
});
