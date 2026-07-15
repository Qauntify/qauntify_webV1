import type { FloorContextBlocks } from "./prompts";

export type SignalSnapshot = {
  symbol: string;
  timeframe: string;
  direction: string;
  status: string;
  entry: number;
  stopLoss: number;
  takeProfit: number;
};

export function formatSignalsBlock(rows: SignalSnapshot[]): string {
  if (!rows.length) return "No open or recent closed signals.";
  return rows
    .slice(0, 20)
    .map(
      (r) =>
        `- ${r.symbol} ${r.timeframe} ${r.direction} status=${r.status} ` +
        `entry=${r.entry} sl=${r.stopLoss} tp1=${r.takeProfit}`,
    )
    .join("\n");
}

export function emptyContext(): FloorContextBlocks {
  return {
    sessionLine: "Market session: unavailable",
    calendarBlock: "Calendar unavailable.",
    headlinesBlock: "No headlines.",
    signalsBlock: "No open or recent closed signals.",
    peerBriefsBlock: "",
  };
}

/** Soft-fill context: callers pass whatever they could fetch. */
export function buildContextBlocks(partial: Partial<FloorContextBlocks>): FloorContextBlocks {
  return { ...emptyContext(), ...partial };
}
