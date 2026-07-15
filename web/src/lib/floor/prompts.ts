import type { FloorDesk } from "./types";

export type FloorContextBlocks = {
  sessionLine: string;
  calendarBlock: string;
  headlinesBlock: string;
  signalsBlock: string;
  peerBriefsBlock: string;
};

const DESK_JOB: Record<FloorDesk, string> = {
  macro:
    "You are the Macro/Session desk. Focus on FX session fit and calendar risk. Do not invent entries.",
  technical:
    "You are the Technical desk. Summarize bias from provided open/recent signal levels only. Do not invent candles or new setups.",
  news:
    "You are the News desk. Summarize catalysts from headlines vs symbols. Flag conflicts, do not invent news.",
  pm:
    "You are the PM/Risk desk. Synthesize peer desk notes into agreement, conflict, and size caution. Do not place trades.",
};

export function buildDeskMessages(
  desk: FloorDesk,
  ctx: FloorContextBlocks,
): { role: "system" | "user"; content: string }[] {
  const system =
    `${DESK_JOB[desk]}\n` +
    "Respond with ONLY JSON: " +
    '{"tone":"bullish"|"neutral"|"cautious","body":"<one short paragraph max 500 chars>"}';

  const user =
    `Desk assignment: ${desk}\n\n` +
    `${ctx.sessionLine}\n\n` +
    `Economic calendar:\n${ctx.calendarBlock}\n\n` +
    `Headlines:\n${ctx.headlinesBlock}\n\n` +
    `Signals book (read-only):\n${ctx.signalsBlock}\n` +
    (ctx.peerBriefsBlock
      ? `\nPeer desk notes:\n${ctx.peerBriefsBlock}\n`
      : "");

  return [
    { role: "system", content: system },
    { role: "user", content: user },
  ];
}

export function buildPmChatMessages(input: {
  question: string;
  boardPack: string;
  signalsBlock: string;
}): { role: "system" | "user"; content: string }[] {
  return [
    {
      role: "system",
      content:
        "You are the Trading Floor PM. Answer the member using the current desk board and open-book snapshot. " +
        "Be concise. Do not claim to execute trades. Respond with ONLY JSON: " +
        '{"tone":"bullish"|"neutral"|"cautious","body":"<answer>"}',
    },
    {
      role: "user",
      content:
        `Question: ${input.question}\n\n` +
        `Current board:\n${input.boardPack}\n\n` +
        `Signals book:\n${input.signalsBlock}`,
    },
  ];
}
