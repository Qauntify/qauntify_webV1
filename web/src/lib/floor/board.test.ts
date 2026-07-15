import { describe, expect, it } from "vitest";

import { runFloorBoardCycle } from "./board";

const context = {
  sessionLine: "Market session: London",
  calendarBlock: "Calendar unavailable.",
  headlinesBlock: "No headlines.",
  signalsBlock: "No open or recent closed signals.",
  peerBriefsBlock: "",
};

describe("runFloorBoardCycle", () => {
  it("saves PM after all peer desks", async () => {
    const saved: string[] = [];
    const chat = async (messages: { content: string }[]) => {
      const desk = messages[1].content.match(/Desk assignment: (\w+)/)?.[1];
      return JSON.stringify({ tone: "neutral", body: `${desk} brief` });
    };

    const result = await runFloorBoardCycle({
      loadContext: async () => context,
      insertBrief: async ({ desk }) => {
        saved.push(desk);
      },
      chat,
    });

    expect(result.failed).toEqual([]);
    expect(saved).toEqual(["macro", "technical", "news", "pm"]);
    expect(result.saved).toEqual(["macro", "technical", "news", "pm"]);
  });

  it("soft-fails an early desk and still completes PM", async () => {
    const saved: string[] = [];
    const chat = async (messages: { content: string }[]) => {
      const desk = messages[1].content.match(/Desk assignment: (\w+)/)?.[1];
      if (desk === "technical") throw new Error("technical unavailable");
      return JSON.stringify({ tone: "neutral", body: `${desk} brief` });
    };

    const result = await runFloorBoardCycle({
      loadContext: async () => context,
      insertBrief: async ({ desk }) => {
        saved.push(desk);
      },
      chat,
    });

    expect(result.failed).toEqual(["technical"]);
    expect(saved).toEqual(["macro", "news", "pm"]);
    expect(result.saved).toEqual(["macro", "news", "pm"]);
  });
});
