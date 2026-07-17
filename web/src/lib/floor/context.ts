import type { FloorContextBlocks } from "./prompts";

export function emptyContext(): FloorContextBlocks {
  return {
    sessionLine: "Market session: unavailable",
    calendarBlock: "Calendar unavailable.",
    headlinesBlock: "No headlines.",
    marketBlock: "Market data unavailable.",
    peerBriefsBlock: "",
  };
}

export function buildContextBlocks(partial: Partial<FloorContextBlocks>): FloorContextBlocks {
  return { ...emptyContext(), ...partial };
}
