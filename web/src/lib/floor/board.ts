import { randomUUID } from "crypto";

import { floorChat, parseDeskBrief } from "./llm";
import { buildDeskMessages, type FloorContextBlocks } from "./prompts";
import { FLOOR_DESKS, type FloorBrief, type FloorDesk, type FloorTone } from "./types";

export async function latestBriefsByDesk(
  fetchLatest: (desk: FloorDesk) => Promise<FloorBrief | null>,
): Promise<Partial<Record<FloorDesk, FloorBrief>>> {
  const briefs: Partial<Record<FloorDesk, FloorBrief>> = {};

  for (const desk of FLOOR_DESKS) {
    const brief = await fetchLatest(desk);
    if (brief) briefs[desk] = brief;
  }

  return briefs;
}

type BoardCycleDependencies = {
  loadContext: () => Promise<FloorContextBlocks>;
  insertBrief: (brief: {
    desk: FloorDesk;
    tone: FloorTone;
    body: string;
    runId: string;
  }) => Promise<void>;
  chat?: typeof floorChat;
};

export async function runFloorBoardCycle(
  deps: BoardCycleDependencies,
): Promise<{ runId: string; saved: FloorDesk[]; failed: FloorDesk[] }> {
  const runId = randomUUID();
  const context = await deps.loadContext();
  const chat = deps.chat ?? floorChat;
  const saved: FloorDesk[] = [];
  const failed: FloorDesk[] = [];
  const peerNotes: string[] = [];

  for (const desk of FLOOR_DESKS.filter((item) => item !== "pm")) {
    try {
      const brief = parseDeskBrief(await chat(buildDeskMessages(desk, context)));
      await deps.insertBrief({ desk, ...brief, runId });
      peerNotes.push(`${desk} (${brief.tone}): ${brief.body}`);
      saved.push(desk);
    } catch {
      failed.push(desk);
    }
  }

  try {
    const brief = parseDeskBrief(
      await chat(
        buildDeskMessages("pm", {
          ...context,
          peerBriefsBlock: peerNotes.join("\n") || "No peer notes this run.",
        }),
      ),
    );
    await deps.insertBrief({ desk: "pm", ...brief, runId });
    saved.push("pm");
  } catch {
    failed.push("pm");
  }

  return { runId, saved, failed };
}
