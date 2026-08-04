import { NextResponse } from "next/server";

import { applyTickEvents } from "@/lib/outcome-apply";
import { sendTelegramMessage } from "@/lib/outcome-alert";
import { checkTickOutcome } from "@/lib/outcome-rules";
import {
  getOpenSignalsForSymbol,
  invalidateOpenSignalsCache,
  updateSignalOutcomeClaim,
} from "@/lib/supabase/admin";
import { authorizedBySecret } from "@/lib/webhook-guard";

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  if (!authorizedBySecret(request, "MT5_WEBHOOK_SECRET")) {
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

  // Independent per-row claims -- run concurrently rather than serializing
  // Supabase/Telegram round-trips for every open signal on this symbol.
  const results = await Promise.all(
    rows.map(async (row) => {
      const events = checkTickOutcome(row, price, closedAtIso);
      if (events.length === 0) return false;
      const { latest } = await applyTickEvents(row, events, deps);
      return latest !== null;
    }),
  );
  const closed = results.filter(Boolean).length;
  if (closed > 0) invalidateOpenSignalsCache(symbol);

  return NextResponse.json({ ok: true, checked: rows.length, closed });
}
