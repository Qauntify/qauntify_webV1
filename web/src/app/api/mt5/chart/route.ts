import { NextResponse } from "next/server";

import { parseMt5ChartBody } from "@/lib/mt5-signal";
import {
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
  if (!patched) {
    return NextResponse.json(
      { error: "Failed to store chart url", url },
      { status: 502 },
    );
  }

  return NextResponse.json({ ok: true, id: parsed.signalId, url, kind: parsed.kind });
}
