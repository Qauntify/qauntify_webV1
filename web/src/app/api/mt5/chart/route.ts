import { NextResponse } from "next/server";

import { tightFrameSetupPng } from "@/lib/mt5-chart-frame";
import { parseMt5ChartBody } from "@/lib/mt5-signal";
import { renderSetupChartPng } from "@/lib/mt5-setup-chart";
import {
  formatSignalAlert,
  sendTelegramPhoto,
} from "@/lib/outcome-alert";
import {
  getMt5CandleSeries,
  getSignalAlertRow,
  getSignalSetupRow,
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

  let png = parsed.png;
  let rendered = false;

  // Prefer a drawn OHLC chart — VPS ChartScreenShot can't hold zoom on M1.
  if (parsed.kind === "setup") {
    try {
      const row = await getSignalSetupRow(parsed.signalId);
      if (row) {
        const candles = await getMt5CandleSeries(row.symbol, row.timeframe);
        if (candles && candles.length > 0) {
          const drawn = await renderSetupChartPng(
            {
              symbol: row.symbol,
              timeframe: row.timeframe,
              direction: row.direction,
              entry: row.entry,
              stop_loss: row.stop_loss,
              take_profit: row.take_profit_1 ?? row.take_profit,
              take_profit_2: row.take_profit_2,
              take_profit_3: row.take_profit_3,
              indicators: row.indicators,
              created_at: row.created_at,
            },
            candles,
          );
          if (drawn) {
            png = drawn;
            rendered = true;
          }
        }
      }
    } catch (err) {
      console.error("[mt5/chart] setup render failed, using EA png", err);
    }
  }

  if (!rendered && parsed.kind === "setup" && parsed.tightFrame) {
    try {
      png = await tightFrameSetupPng(png);
    } catch (err) {
      console.error("[mt5/chart] tight frame failed, using original", err);
    }
  }

  const url = await uploadSignalChartPng(
    parsed.signalId,
    png,
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
    rendered,
  });
}
