import { randomUUID } from "crypto";
import { NextResponse } from "next/server";

import { parseMt5SignalBody } from "@/lib/mt5-signal";
import {
  hasOpenLiveSignal,
  insertLiveSignal,
  invalidateOpenSignalsCache,
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

  const parsed = parseMt5SignalBody(raw);
  if ("error" in parsed) {
    return NextResponse.json({ error: parsed.error }, { status: 400 });
  }

  const open = await hasOpenLiveSignal(parsed.symbol, parsed.timeframe);
  if (open === null) {
    return NextResponse.json({ error: "Storage unavailable" }, { status: 503 });
  }
  if (open) {
    return NextResponse.json(
      { error: "Open signal already exists for symbol+timeframe" },
      { status: 409 },
    );
  }

  const id = randomUUID();
  const createdAt = new Date().toISOString();
  const saved = await insertLiveSignal({
    id,
    symbol: parsed.symbol,
    timeframe: parsed.timeframe,
    direction: parsed.direction,
    entry: parsed.entry,
    stop_loss: parsed.stop_loss,
    take_profit: parsed.take_profit,
    take_profit_1: parsed.take_profit,
    take_profit_2: parsed.take_profit_2,
    take_profit_3: parsed.take_profit_3,
    confidence: parsed.confidence,
    rationale: parsed.rationale,
    indicators: parsed.indicators,
    news_headlines: [],
    created_at: createdAt,
    shadow: false,
    experiment: null,
  });
  if (!saved) {
    return NextResponse.json({ error: "Failed to store signal" }, { status: 502 });
  }

  invalidateOpenSignalsCache(parsed.symbol);

  // Telegram photo is sent from /api/mt5/chart after ChartScreenShot lands
  // (same path as gold Scalp/Swing/War Room). Avoid a text-only duplicate.
  return NextResponse.json({ ok: true, id, telegram: false });
}
