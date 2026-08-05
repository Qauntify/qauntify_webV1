import { NextResponse } from "next/server";

import { applyTickEvents } from "@/lib/outcome-apply";
import { sendTelegramMessage } from "@/lib/outcome-alert";
import { checkTickOutcome } from "@/lib/outcome-rules";
import {
  getOpenSignalsForSymbol,
  invalidateOpenSignalsCache,
  updateSignalOutcomeClaim,
  upsertMt5LastTick,
} from "@/lib/supabase/admin";
import { authorizedBySecret } from "@/lib/webhook-guard";

export const dynamic = "force-dynamic";

type TickBody = {
  symbol: string;
  time: number;
  price?: number;
  bid?: number;
  ask?: number;
  mid?: number;
};

function parseQuotes(body: TickBody): { bid: number; ask: number; mid: number } | null {
  const bid = Number(body.bid ?? body.price);
  const ask = Number(body.ask ?? body.price);
  const midRaw = body.mid != null ? Number(body.mid) : NaN;
  const mid = Number.isFinite(midRaw) ? midRaw : (bid + ask) / 2;
  if (!Number.isFinite(bid) || !Number.isFinite(ask) || bid <= 0 || ask <= 0) {
    return null;
  }
  // Allow tiny inverted quotes from feed glitches by swapping.
  if (ask < bid) {
    return { bid: ask, ask: bid, mid: (ask + bid) / 2 };
  }
  return { bid, ask, mid };
}

export async function POST(request: Request) {
  if (!authorizedBySecret(request, "MT5_WEBHOOK_SECRET")) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  let symbol: string;
  let time: number;
  let quotes: { bid: number; ask: number; mid: number };
  try {
    const body = (await request.json()) as TickBody;
    symbol = String(body.symbol);
    time = Number(body.time);
    const parsed = parseQuotes(body);
    if (!symbol || !Number.isFinite(time) || !parsed) {
      throw new Error("invalid body");
    }
    quotes = parsed;
  } catch {
    return NextResponse.json({ error: "Bad request" }, { status: 400 });
  }

  // Always persist broker quotes so the engine can require a fresh MT5 mid.
  await upsertMt5LastTick(symbol, quotes, time);

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

  const results = await Promise.all(
    rows.map(async (row) => {
      const events = checkTickOutcome(
        row,
        { bid: quotes.bid, ask: quotes.ask },
        closedAtIso,
      );
      if (events.length === 0) return false;
      const { latest } = await applyTickEvents(row, events, deps);
      return latest !== null;
    }),
  );
  const closed = results.filter(Boolean).length;
  if (closed > 0) invalidateOpenSignalsCache(symbol);

  return NextResponse.json({ ok: true, checked: rows.length, closed });
}
