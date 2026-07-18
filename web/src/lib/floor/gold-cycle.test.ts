import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("./run-control", () => ({
  readFloorRunState: vi.fn(),
  beginCycle: vi.fn(),
  endCycleProgress: vi.fn(),
  incrementFloorCycle: vi.fn(),
  setFloorRunPhase: vi.fn(),
  recordFloorSignal: vi.fn(),
}));
vi.mock("./gold-context", () => ({
  loadGoldFloorContext: vi.fn(),
}));
vi.mock("./llm", () => ({
  floorChat: vi.fn(),
  parseDeskBrief: vi.fn(),
  parsePmDecision: vi.fn(),
}));
vi.mock("./prompts", () => ({ buildDeskMessages: vi.fn() }));
vi.mock("./telegram", () => ({ sendFloorGoldAlert: vi.fn() }));
vi.mock("./store", () => ({ insertFloorBrief: vi.fn() }));

import { runOneGoldCycleIfEnabled } from "./gold-cycle";
import { loadGoldFloorContext } from "./gold-context";
import * as runControl from "./run-control";

const IDLE_STATUS = {
  running: false, runId: null, cycle: 0, phase: "idle" as const,
  lastMessage: "", lastSignal: null,
};

describe("runOneGoldCycleIfEnabled", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("does nothing when the hunter is not enabled", async () => {
    vi.mocked(runControl.readFloorRunState).mockResolvedValue(IDLE_STATUS);

    await runOneGoldCycleIfEnabled();

    expect(runControl.beginCycle).not.toHaveBeenCalled();
    expect(loadGoldFloorContext).not.toHaveBeenCalled();
  });

  it("does nothing when a cycle is already in progress", async () => {
    vi.mocked(runControl.readFloorRunState).mockResolvedValue({
      ...IDLE_STATUS, running: true, runId: "run-1",
    });
    vi.mocked(runControl.beginCycle).mockResolvedValue(false);

    await runOneGoldCycleIfEnabled();

    expect(loadGoldFloorContext).not.toHaveBeenCalled();
  });

  it("always clears in_progress, even when the cycle throws", async () => {
    vi.mocked(runControl.readFloorRunState).mockResolvedValue({
      ...IDLE_STATUS, running: true, runId: "run-1",
    });
    vi.mocked(runControl.beginCycle).mockResolvedValue(true);
    vi.mocked(runControl.incrementFloorCycle).mockRejectedValue(new Error("boom"));

    await expect(runOneGoldCycleIfEnabled()).rejects.toThrow("boom");

    expect(runControl.endCycleProgress).toHaveBeenCalledTimes(1);
  });
});
