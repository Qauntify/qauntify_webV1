import { NextResponse } from "next/server";

import { dispatchEngineWorkflow } from "@/lib/github-engine";

export const dynamic = "force-dynamic";

function authorized(request: Request): boolean {
  const secret = process.env.ENGINE_CRON_SECRET?.trim();
  if (!secret) return false;

  const header = request.headers.get("authorization");
  if (header === `Bearer ${secret}`) return true;

  const url = new URL(request.url);
  return url.searchParams.get("secret") === secret;
}

export async function GET(request: Request) {
  if (!authorized(request)) {
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
