import { NextResponse } from "next/server";

import {
  canonicalMarketSymbol,
  fetchMarketCandles,
  parseMarketInterval,
} from "@/lib/markets/kraken";
import { createClient } from "@/lib/supabase/server";

export async function GET(request: Request) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { searchParams } = new URL(request.url);
  const symbol = canonicalMarketSymbol(searchParams.get("symbol") ?? "BTCUSD");
  const interval = parseMarketInterval(searchParams.get("interval"));

  if (!/^[A-Z0-9]{3,20}$/.test(symbol)) {
    return NextResponse.json({ error: "Invalid symbol" }, { status: 400 });
  }

  try {
    const candles = await fetchMarketCandles(symbol, interval);
    return NextResponse.json({ symbol, interval, candles });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Failed to fetch candles";
    return NextResponse.json({ error: message }, { status: 502 });
  }
}
