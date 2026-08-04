import { NextResponse } from "next/server";

import { applyTickEvents } from "@/lib/outcome-apply";
import { sendTelegramMessage } from "@/lib/outcome-alert";
import { checkTickOutcome } from "@/lib/outcome-rules";
import { getOpenSignalsForSymbol, updateSignalOutcomeClaim } from "@/lib/supabase/admin";

export const dynamic = "force-dynamic";

function authorized(request: Request): boolean {
  const secret = process.env.MT5_WEBHOOK_SECRET?.trim();
  if (!secret) return false;
  return request.headers.get("authorization") === `Bearer ${secret}`;
}

export async function POST(request: Request) {
  if (!authorized(request)) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  let symbol: string;
  let price: number;
  let time: number;
  try {
    const body = (await request.json()) as { symbol: string; price: number; time: number };
    symbol = String(body.symbol);
    price = Number(body.price);
    time = Number(body.time);
    if (!symbol || !Number.isFinite(price) || !Number.isFinite(time)) {
      throw new Error("invalid body");
    }
  } catch {
    return NextResponse.json({ error: "Bad request" }, { status: 400 });
  }

  const rows = await getOpenSignalsForSymbol(symbol);
  if (!rows || rows.length === 0) {
    return NextResponse.json({ ok: true, checked: 0, closed: 0 });
  }

  const closedAtIso = new Date(time * 1000).toISOString();
  const deps = {
    updateSignalOutcomeClaim,
    sendTelegramMessage,
    telegramBotToken: process.env.TELEGRAM_BOT_TOKEN?.trim() ?? "",
    telegramChannelId:
      (process.env.TELEGRAM_CHANNEL_ID || process.env.TELEGRAM_CHAT_ID)?.trim() ?? "",
  };

  let closed = 0;
  for (const row of rows) {
    const events = checkTickOutcome(row, price, closedAtIso);
    if (events.length === 0) continue;
    const { latest } = await applyTickEvents(row, events, deps);
    if (latest !== null) closed += 1;
  }

  return NextResponse.json({ ok: true, checked: rows.length, closed });
}
