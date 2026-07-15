import { describe, expect, it } from "vitest";
import { buildDeskMessages, buildPmChatMessages } from "./prompts";

describe("floor prompts", () => {
  it("builds macro desk messages with calendar block", () => {
    const msgs = buildDeskMessages("macro", {
      sessionLine: "Market session: London",
      calendarBlock: "- USD CPI High",
      headlinesBlock: "- Cable soft",
      signalsBlock: "No open signals",
      peerBriefsBlock: "",
    });
    expect(msgs[0].role).toBe("system");
    expect(msgs[1].content).toContain("macro");
    expect(msgs[1].content).toContain("USD CPI");
  });

  it("PM chat includes board pack", () => {
    const msgs = buildPmChatMessages({
      question: "Is GBP risk-on right now?",
      boardPack: "macro: cautious — ...\nnews: neutral — ...",
      signalsBlock: "Open: none",
    });
    expect(msgs[1].content).toContain("GBP");
    expect(msgs[1].content).toContain("board");
  });
});
