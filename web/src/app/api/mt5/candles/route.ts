import { NextResponse } from "next/server";

import { shouldDispatchEngineFromM1Push } from "@/lib/bar-close";
import { dispatchEngineWorkflow } from "@/lib/github-engine";
import { mergeMt5Candles } from "@/lib/supabase/admin";
import { authorizedBySecret } from "@/lib/webhook-guard";

export const dynamic = "force-dynamic";

type CandleIn = {
  open_time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
};

type Body = {
  symbol: string;
  timeframe?: string;
  candles?: Array<{
    open_time: number;
    open: number;
    high: number;
    low: number;
    close: number;
    volume?: number;
  }>;
  // single-candle shorthand
  open_time?: number;
  open?: number;
  high?: number;
  low?: number;
  close?: number;
  volume?: number;
};

function normalizeCandle(c: {
  open_time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
}): CandleIn | null {
  const open_time = Number(c.open_time);
  const open = Number(c.open);
  const high = Number(c.high);
  const low = Number(c.low);
  const close = Number(c.close);
  const volume = Number(c.volume ?? 0);
  if (
    !Number.isFinite(open_time) ||
    !Number.isFinite(open) ||
    !Number.isFinite(high) ||
    !Number.isFinite(low) ||
    !Number.isFinite(close) ||
    open_time <= 0
  ) {
    return null;
  }
  return {
    open_time: Math.floor(open_time),
    open,
    high,
    low,
    close,
    volume: Number.isFinite(volume) ? volume : 0,
  };
}

export async function POST(request: Request) {
  if (!authorizedBySecret(request, "MT5_WEBHOOK_SECRET")) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  let symbol: string;
  let timeframe: string;
  let candles: CandleIn[];
  try {
    const body = (await request.json()) as Body;
    symbol = String(body.symbol || "").trim().toUpperCase();
    timeframe = String(body.timeframe || "1m").trim();
    const raw = Array.isArray(body.candles)
      ? body.candles
      : body.open_time != null
        ? [
            {
              open_time: body.open_time,
              open: body.open!,
              high: body.high!,
              low: body.low!,
              close: body.close!,
              volume: body.volume,
            },
          ]
        : [];
    candles = raw
      .map((c) => normalizeCandle(c))
      .filter((c): c is CandleIn => c != null);
    if (!symbol || timeframe !== "1m" || candles.length === 0) {
      throw new Error("invalid body");
    }
  } catch {
    return NextResponse.json({ error: "Bad request" }, { status: 400 });
  }

  const ok = await mergeMt5Candles(symbol, timeframe, candles);
  if (!ok) {
    return NextResponse.json({ error: "Persist failed" }, { status: 502 });
  }

  // VPS runs EA only — on 5m/15m/1h close, kick GitHub Actions engine.
  // Soft-fail: candle storage already succeeded; never 5xx for dispatch.
  const due = shouldDispatchEngineFromM1Push(candles);
  let engine: "skipped" | "dispatched" | "failed" = "skipped";
  if (due.length > 0) {
    try {
      const result = await dispatchEngineWorkflow();
      engine = result.ok ? "dispatched" : "failed";
    } catch {
      engine = "failed";
    }
  }

  return NextResponse.json({
    ok: true,
    merged: candles.length,
    engine,
    due,
  });
}
