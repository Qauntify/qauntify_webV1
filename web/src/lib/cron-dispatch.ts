import { NextResponse } from "next/server";

import type { DispatchResult } from "@/lib/github-engine";
import { authorizedBySecret } from "@/lib/webhook-guard";

/** Shared GET/POST handler for cron-job.org → GitHub dispatch routes. */
export async function handleCronDispatch(
  request: Request,
  dispatch: () => Promise<DispatchResult>,
  triggered: string,
): Promise<NextResponse> {
  if (!authorizedBySecret(request, "ENGINE_CRON_SECRET", { allowQuerySecret: true })) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const result = await dispatch();
  if (!result.ok) {
    return NextResponse.json(
      { error: "Dispatch failed", detail: result.message },
      { status: result.status === 500 ? 500 : 502 },
    );
  }

  return NextResponse.json({ ok: true, triggered });
}
