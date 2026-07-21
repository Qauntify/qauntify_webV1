import { floorChat, parseDeskBrief, parsePmDecision } from "./llm";
import { buildDeskMessages } from "./prompts";
import { sendFloorGoldAlert } from "./telegram";
import {
  beginCycle,
  endCycleProgress,
  incrementFloorCycle,
  readFloorRunState,
  recordFloorSignal,
  setFloorRunPhase,
} from "./run-control";
import { insertFloorBrief } from "./store";
import { loadGoldFloorContext } from "./gold-context";
import { FLOOR_DESKS, GOLD_SYMBOL, type FloorTone } from "./types";

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
  const cycle = await incrementFloorCycle();
  const context = await loadGoldFloorContext();
  const peerNotes: string[] = [];

  for (const desk of FLOOR_DESKS.filter((item) => item !== "pm")) {
    await setFloorRunPhase(desk, `Cycle ${cycle}: ${desk} desk analyzing gold...`);
    try {
      const brief = parseDeskBrief(
        await floorChat(buildDeskMessages(desk, context), { desk }),
      );
      await insertFloorBrief({ desk, ...brief, runId });
      peerNotes.push(`${desk} (${brief.tone}): ${brief.body}`);
    } catch {
      const fallback = `${desk} desk unavailable this cycle.`;
      await insertFloorBrief({ desk, tone: "neutral", body: fallback, runId });
    }
  }

  await setFloorRunPhase("pm", `Cycle ${cycle}: PM deciding signal or pass...`);
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
    await insertFloorBrief({ desk: "pm", tone: pmTone, body: pmText, runId });

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
      await recordFloorSignal(signal);
      const alerted = await sendFloorGoldAlert({
        symbol: GOLD_SYMBOL,
        ...signal,
        rationale: decision.body,
      });
      const alertMsg = alerted
        ? `Cycle ${cycle}: SIGNAL dropped — Telegram sent.`
        : `Cycle ${cycle}: SIGNAL dropped — saved on floor.`;
      await setFloorRunPhase("pm", alertMsg);
      return;
    }

    await setFloorRunPhase("pm", `Cycle ${cycle}: PASS — no signal this round.`);
  } catch {
    const fallback = "PM desk unavailable this cycle.";
    await insertFloorBrief({ desk: "pm", tone: "neutral", body: fallback, runId });
    await setFloorRunPhase("pm", `Cycle ${cycle}: PM error — pass by default.`);
  }
}

/**
 * Runs exactly one gold-hunt cycle if the hunter is enabled and no other
 * invocation (manual or cron) currently has one in progress. Called
 * identically from the Run button (immediate, awaited) and the cron
 * endpoint (on its external schedule) — this is the only place either
 * trigger touches cycle logic.
 */
export async function runOneGoldCycleIfEnabled(): Promise<void> {
  const state = await readFloorRunState();
  if (!state.running || !state.runId) return;

  const started = await beginCycle();
  if (!started) return;

  try {
    await runOneGoldCycle(state.runId);
  } finally {
    await endCycleProgress();
  }
}
