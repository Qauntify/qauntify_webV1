/** Ported from signals/telegram_client.py — the outcome (TP/SL hit) alert
 * only. Text-only: the photo-caption branch (send_photo) is never reached
 * from the realtime MT5 path, since outcome_chart_url is always null at the
 * moment of a live hit (see docs/plan — charts are backfilled separately). */
import type { SignalRow } from "./outcome-rules";

const DIVIDER = "━━━━━━━━━━━━━━━━━━━━";

const OUTCOME_META: Record<string, [emoji: string, title: string, nextHint: string]> = {
  sl_hit: ["🛑", "STOP LOSS", ""],
  tp1_hit: ["✅", "TP1 HIT", "Next target: TP2 🎯"],
  tp2_hit: ["✅", "TP2 HIT", "Next target: TP3 🎯"],
  tp3_hit: ["🏆", "TP3 HIT", "Final target reached 🎉"],
  tp_hit: ["🏆", "TAKE PROFIT", "Target reached 🎉"],
};

function esc(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function price(value: number): string {
  return `<code>${value}</code>`;
}

function directionArrow(direction: string): string {
  return direction === "long" ? "▲" : "▼";
}

function directionDot(direction: string): string {
  return direction === "long" ? "🟢" : "🔴";
}

export function formatOutcomeAlert(row: SignalRow, outcome: string): string {
  const entry = row.entry;
  const direction = row.direction;
  const directionLabel = esc(direction.toUpperCase());
  const symbol = esc(row.symbol);
  const arrow = directionArrow(direction);
  const dot = directionDot(direction);
  const [emoji, title, nextHint] =
    OUTCOME_META[outcome] ?? ["•", outcome.toUpperCase().replace(/_/g, " "), ""];

  let exitPrice: number;
  if (outcome === "sl_hit") {
    exitPrice = row.stop_loss;
  } else {
    const tpMap: Record<string, number | null | undefined> = {
      tp1_hit: row.take_profit_1 ?? row.take_profit,
      tp2_hit: row.take_profit_2,
      tp3_hit: row.take_profit_3,
      tp_hit: row.take_profit_3 ?? row.take_profit,
    };
    exitPrice = tpMap[outcome] ?? row.take_profit ?? 0;
  }

  let move = ((exitPrice - entry) / entry) * 100;
  if (direction === "short") move = -move;
  const trend = move >= 0 ? "📈" : "📉";

  const lines = [
    `${emoji} <b>${title}</b>`,
    DIVIDER,
    `${dot} <b>${symbol}</b>  ·  <b>${arrow} ${directionLabel}</b>  ·  ` +
      `${trend} <b>${move >= 0 ? "+" : ""}${move.toFixed(2)}%</b>`,
  ];
  if (nextHint) lines.push("", `<i>${nextHint}</i>`);
  lines.push("", `📍 <b>Exit</b>`, `Entry  ${price(entry)}  →  ${price(exitPrice)}`);
  return lines.join("\n");
}

export async function sendTelegramMessage(
  text: string,
  botToken: string,
  chatId: string,
): Promise<void> {
  const response = await fetch(`https://api.telegram.org/bot${botToken}/sendMessage`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, text, parse_mode: "HTML" }),
  });
  if (!response.ok) {
    let detail = "";
    try {
      const body = (await response.json()) as { description?: string };
      detail = body.description ?? "";
    } catch {
      detail = (await response.text()).slice(0, 200);
    }
    throw new Error(
      `${response.status} Telegram message failed` + (detail ? `: ${detail}` : ""),
    );
  }
}
