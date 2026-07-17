import { randomUUID } from "crypto";

import { fetchCalendarBlock } from "./calendar";
import { fetchGoldMarketBlock } from "./market";
import { fetchHeadlinesBlock } from "./news";
import { describeMarketSession } from "./session";
import { buildContextBlocks, emptyContext } from "./context";
import type { FloorContextBlocks } from "./prompts";

export async function loadGoldFloorContext(): Promise<FloorContextBlocks> {
  const [calendarBlock, headlinesBlock, marketBlock] = await Promise.all([
    fetchCalendarBlock(),
    fetchHeadlinesBlock(),
    fetchGoldMarketBlock(),
  ]);

  return buildContextBlocks({
    sessionLine: describeMarketSession(),
    calendarBlock,
    headlinesBlock,
    marketBlock,
  });
}

export function newGoldRunId(): string {
  return `${randomUUID()}-gold`;
}

export { emptyContext };
