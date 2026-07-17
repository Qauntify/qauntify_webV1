import { NextResponse } from "next/server";

import { requireAdminApi } from "@/lib/admin-api-guard";
import { floorRunSnapshot, requestFloorStop } from "@/lib/floor/run-control";

export const dynamic = "force-dynamic";

export async function POST() {
  const denied = await requireAdminApi();
  if (denied) return denied;

  requestFloorStop();
  return NextResponse.json({
    ok: true,
    ...floorRunSnapshot(),
    message: "Stop requested. The hunter will halt after the current step.",
  });
}
