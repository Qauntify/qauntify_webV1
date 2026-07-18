import { NextResponse } from "next/server";

import { requireAdminApi } from "@/lib/admin-api-guard";
import { disableFloorRun, readFloorRunState } from "@/lib/floor/run-control";

export const dynamic = "force-dynamic";

export async function POST() {
  const denied = await requireAdminApi();
  if (denied) return denied;

  await disableFloorRun();
  return NextResponse.json({
    ok: true,
    ...(await readFloorRunState()),
    message: "Stop requested. No further cycles will start.",
  });
}
