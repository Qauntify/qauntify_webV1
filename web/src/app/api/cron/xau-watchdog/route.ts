import { NextResponse } from "next/server";

import { dispatchXauScalperRestart } from "@/lib/github-engine";
import { getXauScanStatus } from "@/lib/supabase/admin";

export const dynamic = "force-dynamic";

function authorized(request: Request): boolean {
  const secret = process.env.ENGINE_CRON_SECRET?.trim();
  if (!secret) return false;

  const header = request.headers.get("authorization");
  if (header === `Bearer ${secret}`) return true;

  // cron-job.org stores the secret in the URL query string.
  const querySecret = new URL(request.url).searchParams.get("secret");
  return querySecret === secret;
}

export async function GET(request: Request) {
  if (!authorized(request)) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const status = await getXauScanStatus();
  if (status && status.isHealthy) {
    return NextResponse.json({
      ok: true,
      action: "skipped",
      ageMinutes: status.ageMinutes,
    });
  }

  const result = await dispatchXauScalperRestart();
  if (!result.ok) {
    return NextResponse.json(
      { error: "Dispatch failed", detail: result.message },
      { status: result.status === 500 ? 500 : 502 },
    );
  }

  return NextResponse.json({
    ok: true,
    action: "restarted",
    ageMinutes: status?.ageMinutes ?? null,
  });
}

export async function POST(request: Request) {
  return GET(request);
}
