import type { Signal } from "@/lib/signals";
import type { GoldScanOutcome, FloorBrief, FloorDesk, FloorTone } from "./types";

const TIMEFRAME_DESK: Record<string, FloorDesk> = {
  "5m": "macro",
  "15m": "technical",
  "1h": "pm",
};

function toneForOutcome(outcome: GoldScanOutcome): FloorTone {
  if (outcome.status !== "CONFIRMED") return "neutral";
  return outcome.direction === "long" ? "bullish" : "cautious";
}

function bodyForOutcome(outcome: GoldScanOutcome): string {
  if (outcome.status === "CONFIRMED") {
    const parts = [
      `${outcome.direction?.toUpperCase() ?? "SETUP"} ${outcome.confidence ?? 0}%`,
      `entry ${outcome.entry}`,
      `SL ${outcome.stopLoss}`,
      `TP ${outcome.takeProfit}`,
    ];
    if (outcome.rationale) parts.push(outcome.rationale);
    if (outcome.alerted) parts.push("Telegram alert sent.");
    return parts.join(" — ");
  }
  return outcome.rationale?.trim() || `${outcome.status} on ${outcome.timeframe}.`;
}

export function buildFloorBriefsFromScan(input: {
  runId: string;
  outcomes: GoldScanOutcome[];
  headlines: string[];
}): Array<{ desk: FloorDesk; tone: FloorTone; body: string; runId: string }> {
  const briefs: Array<{ desk: FloorDesk; tone: FloorTone; body: string; runId: string }> = [];

  for (const outcome of input.outcomes) {
    const desk = TIMEFRAME_DESK[outcome.timeframe];
    if (!desk) continue;
    briefs.push({
      desk,
      tone: toneForOutcome(outcome),
      body: bodyForOutcome(outcome),
      runId: input.runId,
    });
  }

  const headlineBody = input.headlines.length
    ? input.headlines.map((title) => `- ${title}`).join("\n")
    : "No gold headlines this run.";
  briefs.push({
    desk: "news",
    tone: "neutral",
    body: headlineBody,
    runId: input.runId,
  });

  return briefs;
}

export function formatScanStatus(outcomes: GoldScanOutcome[]): string {
  const confirmed = outcomes.filter((item) => item.status === "CONFIRMED").length;
  if (confirmed > 0) {
    return `${confirmed} gold signal${confirmed === 1 ? "" : "s"} confirmed this run.`;
  }
  return "No new gold signal this run.";
}

export type GoldFloorBoardData = {
  symbol: string;
  desks: FloorBrief[];
  signals: Signal[];
  scanLine: string;
};
