import type { FloorDesk } from "./types";

export type FloorContextBlocks = {
  sessionLine: string;
  calendarBlock: string;
  headlinesBlock: string;
  marketBlock: string;
  peerBriefsBlock: string;
};

const DESK_JOB: Record<FloorDesk, string> = {
  macro:
    "You are the Gold Macro desk for PAXGUSDT. Read session and calendar risk for gold. Do not invent prices.",
  technical:
    "You are the Gold Technical desk for PAXGUSDT. Read the market block and infer structure bias only from provided numbers.",
  news:
    "You are the Gold News desk. Summarize headline catalysts for gold. Do not invent news.",
  pm:
    "You are the Gold PM desk. You alone decide whether to DROP a trade signal this cycle or PASS. " +
    "Use peer desk notes plus market context. Never reuse the main engine — this is an independent gold floor decision.",
};

export function buildDeskMessages(
  desk: FloorDesk,
  ctx: FloorContextBlocks,
): { role: "system" | "user"; content: string }[] {
  if (desk === "pm") {
    return [
      {
        role: "system",
        content:
          `${DESK_JOB.pm}\n` +
          "Respond with ONLY JSON:\n" +
          '{"action":"signal"|"pass","tone":"bullish"|"neutral"|"cautious","body":"<short rationale>",' +
          '"direction":"long"|"short","entry":number,"stopLoss":number,"takeProfit":number,"confidence":number}\n' +
          "Use action signal only with clear conviction and realistic levels near the market block. Otherwise action pass with direction omitted.",
      },
      {
        role: "user",
        content:
          `Gold symbol: PAXGUSDT\n\n` +
          `${ctx.sessionLine}\n\n` +
          `Economic calendar:\n${ctx.calendarBlock}\n\n` +
          `Headlines:\n${ctx.headlinesBlock}\n\n` +
          `Market:\n${ctx.marketBlock}\n\n` +
          `Peer desk notes:\n${ctx.peerBriefsBlock || "No peer notes."}`,
      },
    ];
  }

  const system =
    `${DESK_JOB[desk]}\n` +
    "Respond with ONLY JSON: " +
    '{"tone":"bullish"|"neutral"|"cautious","body":"<one short paragraph max 500 chars>"}';

  const user =
    `Desk assignment: ${desk}\n` +
    `Gold symbol: PAXGUSDT\n\n` +
    `${ctx.sessionLine}\n\n` +
    `Economic calendar:\n${ctx.calendarBlock}\n\n` +
    `Headlines:\n${ctx.headlinesBlock}\n\n` +
    `Market:\n${ctx.marketBlock}\n` +
    (ctx.peerBriefsBlock ? `\nPeer desk notes:\n${ctx.peerBriefsBlock}\n` : "");

  return [
    { role: "system", content: system },
    { role: "user", content: user },
  ];
}
