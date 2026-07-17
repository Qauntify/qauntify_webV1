import { describe, expect, it } from "vitest";
import { buildDeskMessages } from "./prompts";

describe("floor prompts", () => {
  it("builds macro desk messages with calendar block", () => {
    const msgs = buildDeskMessages("macro", {
      sessionLine: "Market session: London",
      calendarBlock: "- USD CPI High",
      headlinesBlock: "- Cable soft",
      peerBriefsBlock: "",
    });
    expect(msgs[0].role).toBe("system");
    expect(msgs[1].content).toContain("macro");
    expect(msgs[1].content).toContain("USD CPI");
    expect(msgs[1].content).not.toContain("Signals book");
  });
});
