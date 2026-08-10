import { NextResponse } from "next/server";

import { parseMt5ChartBody } from "@/lib/mt5-signal";
import {
  formatSignalAlert,
  sendTelegramPhoto,
} from "@/lib/outcome-alert";
import {
  getSignalAlertRow,
  setSignalChartUrl,
  signalExists,
  uploadSignalChartPng,
} from "@/lib/supabase/admin";
import { authorizedBySecret } from "@/lib/webhook-guard";

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  if (!authorizedBySecret(request, "MT5_WEBHOOK_SECRET")) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  let raw: unknown;
  try {
    raw = await request.json();
  } catch {
    return NextResponse.json({ error: "Bad request" }, { status: 400 });
  }

  const parsed = parseMt5ChartBody(raw);
  if ("error" in parsed) {
    return NextResponse.json({ error: parsed.error }, { status: 400 });
  }

  const exists = await signalExists(parsed.signalId);
  if (exists === null) {
    return NextResponse.json({ error: "Storage unavailable" }, { status: 503 });
  }
  if (!exists) {
    return NextResponse.json({ error: "Signal not found" }, { status: 404 });
  }

  const url = await uploadSignalChartPng(
    parsed.signalId,
    parsed.png,
    parsed.kind,
  );
  if (!url) {
    return NextResponse.json({ error: "Upload failed" }, { status: 502 });
  }

  const patched = await setSignalChartUrl(
    parsed.signalId,
    url,
    parsed.kind,
  );
  if (!patched.ok) {
    return NextResponse.json(
      { error: "Failed to store chart url", url },
      { status: 502 },
    );
  }

  // First setup chart upload → Telegram photo (Python/BBMA defer text for gold).
  let telegram = false;
  if (parsed.kind === "setup" && !patched.previousUrl) {
    const botToken = process.env.TELEGRAM_BOT_TOKEN?.trim() ?? "";
    const chatId =
      (process.env.TELEGRAM_CHANNEL_ID || process.env.TELEGRAM_CHAT_ID)?.trim() ??
      "";
    if (botToken && chatId) {
      try {
        const row = await getSignalAlertRow(parsed.signalId);
        if (row) {
          const tp1 = row.take_profit_1 ?? row.take_profit;
          const tp2 = row.take_profit_2 ?? tp1;
          const tp3 = row.take_profit_3 ?? tp2;
          await sendTelegramPhoto(
            url,
            formatSignalAlert({
              symbol: row.symbol,
              timeframe: row.timeframe,
              direction: row.direction,
              entry: row.entry,
              stopLoss: row.stop_loss,
              takeProfit: tp1,
              takeProfit2: tp2,
              takeProfit3: tp3,
              confidence: row.confidence,
              rationale: row.rationale,
            }),
            botToken,
            chatId,
          );
          telegram = true;
        }
      } catch (err) {
        console.error("[mt5/chart] telegram photo failed", err);
      }
    }
  }

  return NextResponse.json({
    ok: true,
    id: parsed.signalId,
    url,
    kind: parsed.kind,
    telegram,
  });
}
