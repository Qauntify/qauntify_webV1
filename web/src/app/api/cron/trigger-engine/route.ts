import { NextResponse } from "next/server";

import { dispatchEngineWorkflow } from "@/lib/github-engine";
import { authorizedBySecret } from "@/lib/webhook-guard";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  if (!authorizedBySecret(request, "ENGINE_CRON_SECRET", { allowQuerySecret: true })) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const result = await dispatchEngineWorkflow();
  if (!result.ok) {
    return NextResponse.json(
      { error: "Dispatch failed", detail: result.message },
      { status: result.status === 500 ? 500 : 502 },
    );
  }

  return NextResponse.json({ ok: true, triggered: "signals-engine" });
}

export async function POST(request: Request) {
  return GET(request);
}
