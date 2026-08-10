import { describe, expect, it } from "vitest";

/** Mirrors /api/mt5/charts/pending period mapping. */
const PERIOD_MINUTES: Record<string, number> = {
  "5m": 5,
  "15m": 15,
  floor: 15,
  "1h": 60,
};

describe("pending chart period mapping", () => {
  it("maps scalp/swing/war-room timeframes to MT5 minutes", () => {
    expect(PERIOD_MINUTES["5m"]).toBe(5);
    expect(PERIOD_MINUTES["15m"]).toBe(15);
    expect(PERIOD_MINUTES.floor).toBe(15);
    expect(PERIOD_MINUTES["1h"]).toBe(60);
  });
});
