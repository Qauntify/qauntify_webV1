import { describe, expect, it } from "vitest";

import { buildFloorBriefsFromScan } from "./gold-floor";

describe("buildFloorBriefsFromScan", () => {
  it("maps timeframe outcomes to desk briefs", () => {
    const briefs = buildFloorBriefsFromScan({
      runId: "run-1",
      headlines: ["Gold retreats"],
      outcomes: [
        {
          timeframe: "5m",
          status: "CONFIRMED",
          direction: "long",
          confidence: 82,
          entry: 2400,
          stopLoss: 2390,
          takeProfit: 2420,
          rationale: "ICT retest",
          alerted: true,
        },
        {
          timeframe: "15m",
          status: "NO SIGNAL",
          rationale: "No setup",
        },
      ],
    });

    expect(briefs).toHaveLength(3);
    expect(briefs[0].desk).toBe("macro");
    expect(briefs[0].body).toContain("LONG");
    expect(briefs[1].desk).toBe("technical");
    expect(briefs[2].desk).toBe("news");
    expect(briefs[2].body).toContain("Gold retreats");
  });
});
