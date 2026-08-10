import { NextResponse } from "next/server";

import { listPendingSetupCharts } from "@/lib/supabase/admin";
import { authorizedBySecret } from "@/lib/webhook-guard";

export const dynamic = "force-dynamic";

/** Map stored timeframe → MT5 period minutes for the EA. */
const PERIOD_MINUTES: Record<string, number> = {
  "5m": 5,
  "15m": 15,
  floor: 15,
  "1h": 60,
};

export async function GET(request: Request) {
  if (!authorizedBySecret(request, "MT5_WEBHOOK_SECRET")) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const url = new URL(request.url);
  const symbol = (url.searchParams.get("symbol") ?? "").trim().toUpperCase();
  const timeframe = (url.searchParams.get("timeframe") ?? "").trim().toLowerCase();
  const limitRaw = Number(url.searchParams.get("limit") ?? 5);

  if (!symbol) {
    return NextResponse.json({ error: "symbol required" }, { status: 400 });
  }

  const rows = await listPendingSetupCharts(symbol, {
    timeframe: timeframe || undefined,
    limit: Number.isFinite(limitRaw) ? limitRaw : 5,
  });
  if (rows === null) {
    return NextResponse.json({ error: "Storage unavailable" }, { status: 503 });
  }

  const pending = rows.map((r) => ({
    ...r,
    period_minutes: PERIOD_MINUTES[r.timeframe] ?? null,
  }));

  return NextResponse.json({ ok: true, pending });
}
