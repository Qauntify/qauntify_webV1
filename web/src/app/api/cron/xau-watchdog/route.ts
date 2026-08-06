import { NextResponse } from "next/server";

import { dispatchXauScalperRestart } from "@/lib/github-engine";
import { getXauScanStatus } from "@/lib/supabase/admin";
import { authorizedBySecret } from "@/lib/webhook-guard";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  if (!authorizedBySecret(request, "ENGINE_CRON_SECRET", { allowQuerySecret: true })) {
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
    const { formatCronFailAlert, sendOpsTelegram } = await import(
      "@/lib/telegram-ops"
    );
    await sendOpsTelegram(
      formatCronFailAlert({
        job: "xau-watchdog",
        detail: result.message,
        status: result.status,
      }),
    );
    return NextResponse.json(
      { error: "Dispatch failed", detail: result.message },
      { status: result.status === 500 ? 500 : 502 },
    );
  }

  {
    const { formatCronFailAlert, sendOpsTelegram } = await import(
      "@/lib/telegram-ops"
    );
    await sendOpsTelegram(
      formatCronFailAlert({
        job: "xau-watchdog",
        title: "XAU heartbeat stale",
        detail: `Heartbeat stale (${status?.ageMinutes?.toFixed(1) ?? "?"}m) — restarted xau-scalper`,
      }),
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
