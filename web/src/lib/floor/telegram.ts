export async function sendFloorGoldAlert(input: {
  symbol: string;
  direction: "long" | "short";
  entry: number;
  stopLoss: number;
  takeProfit: number;
  confidence: number;
  rationale: string;
}): Promise<boolean> {
  const token = process.env.TELEGRAM_BOT_TOKEN?.trim();
  const chatId = (
    process.env.TELEGRAM_CHANNEL_ID?.trim()
    || process.env.TELEGRAM_CHAT_ID?.trim()
  );
  if (!token || !chatId) return false;

  const text = [
    `<b>${input.direction.toUpperCase()} ${input.symbol}</b> (Gold Floor AI)`,
    `Entry ${input.entry} | SL ${input.stopLoss} | TP ${input.takeProfit}`,
    `Confidence ${input.confidence}%`,
    input.rationale,
  ].join("\n");

  const response = await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      chat_id: chatId,
      text,
      parse_mode: "HTML",
    }),
  });

  return response.ok;
}
