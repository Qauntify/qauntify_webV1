import { floorChat, parseDeskBrief, parsePmDecision } from "./llm";
import { buildDeskMessages } from "./prompts";
import { sendFloorGoldAlert } from "./telegram";
import {
  incrementFloorCycle,
  recordFloorSignal,
  setFloorRunPhase,
  shouldStopFloorRun,
} from "./run-control";
import { insertFloorBrief } from "./store";
import { loadGoldFloorContext } from "./gold-context";
import { FLOOR_DESKS, GOLD_SYMBOL, type FloorTone } from "./types";

const CYCLE_PAUSE_MS = Number(process.env.FLOOR_CYCLE_PAUSE_MS ?? "90_000");

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function pmBody(decision: ReturnType<typeof parsePmDecision>): string {
  if (decision.action !== "signal" || !decision.direction) {
    return `PASS — ${decision.body}`;
  }
  return [
    `SIGNAL ${decision.direction.toUpperCase()} @ ${decision.entry}`,
    `SL ${decision.stopLoss} | TP ${decision.takeProfit}`,
    `Confidence ${decision.confidence ?? 0}%`,
    decision.body,
  ].join(" — ");
}

async function runOneGoldCycle(runId: string): Promise<void> {
  const cycle = incrementFloorCycle();
  const context = await loadGoldFloorContext();
  const peerNotes: string[] = [];

  for (const desk of FLOOR_DESKS.filter((item) => item !== "pm")) {
    if (shouldStopFloorRun()) return;

    setFloorRunPhase(desk, `Cycle ${cycle}: ${desk} desk analyzing gold...`);
    try {
      const brief = parseDeskBrief(
        await floorChat(buildDeskMessages(desk, context), { desk }),
      );
      await insertFloorBrief({ desk, ...brief, runId });
      peerNotes.push(`${desk} (${brief.tone}): ${brief.body}`);
    } catch {
      await insertFloorBrief({
        desk,
        tone: "neutral",
        body: `${desk} desk unavailable this cycle.`,
        runId,
      });
    }
  }

  if (shouldStopFloorRun()) return;

  setFloorRunPhase("pm", `Cycle ${cycle}: PM deciding signal or pass...`);
  let pmTone: FloorTone = "neutral";
  let pmText = "PM unavailable this cycle.";

  try {
    const decision = parsePmDecision(
      await floorChat(
        buildDeskMessages("pm", {
          ...context,
          peerBriefsBlock: peerNotes.join("\n") || "No peer notes.",
        }),
        { desk: "pm" },
      ),
    );
    pmTone = decision.tone;
    pmText = pmBody(decision);
    await insertFloorBrief({
      desk: "pm",
      tone: pmTone,
      body: pmText,
      runId,
    });

    if (
      decision.action === "signal"
      && decision.direction
      && decision.entry
      && decision.stopLoss
      && decision.takeProfit
    ) {
      const signal = {
        direction: decision.direction,
        entry: decision.entry,
        stopLoss: decision.stopLoss,
        takeProfit: decision.takeProfit,
        confidence: decision.confidence ?? 0,
        body: decision.body,
        createdAt: new Date().toISOString(),
      };
      recordFloorSignal(signal);
      const alerted = await sendFloorGoldAlert({
        symbol: GOLD_SYMBOL,
        ...signal,
        rationale: decision.body,
      });
      setFloorRunPhase(
        "pm",
        alerted
          ? `Cycle ${cycle}: SIGNAL dropped — Telegram sent.`
          : `Cycle ${cycle}: SIGNAL dropped — saved on floor.`,
      );
      return;
    }

    setFloorRunPhase("pm", `Cycle ${cycle}: PASS — no signal this round.`);
  } catch {
    await insertFloorBrief({
      desk: "pm",
      tone: "neutral",
      body: "PM desk unavailable this cycle.",
      runId,
    });
    setFloorRunPhase("pm", `Cycle ${cycle}: PM error — pass by default.`);
  }
}

export async function runGoldFloorLoop(runId: string): Promise<void> {
  while (!shouldStopFloorRun()) {
    await runOneGoldCycle(runId);
    if (shouldStopFloorRun()) break;

    setFloorRunPhase("sleeping", "Waiting before next gold hunt cycle...");
    const steps = Math.max(1, Math.floor(CYCLE_PAUSE_MS / 1000));
    for (let step = 0; step < steps; step += 1) {
      if (shouldStopFloorRun()) break;
      await sleep(1000);
    }
  }

  setFloorRunPhase("idle", "Gold hunter stopped.");
}
