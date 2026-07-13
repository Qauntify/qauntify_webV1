import { NextResponse } from "next/server";

import {
  buildClosedSignalsPdf,
  buildClosedSignalsXlsx,
  exportFilename,
  parseExportTab,
  timeframeForTab,
} from "@/lib/export-closed-signals";
import { getClosedOutcomeSignals } from "@/lib/signals";
import { isAdminEmail, serviceRoleToken } from "@/lib/supabase/admin";
import { createClient } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

async function requireAdminApi(): Promise<NextResponse | null> {
  const supabase = await createClient();
  const { data } = await supabase.auth.getUser();
  const email = data.user?.email;
  if (!email) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  if (!isAdminEmail(email)) {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }
  return null;
}

export async function GET(request: Request) {
  const denied = await requireAdminApi();
  if (denied) return denied;

  const url = new URL(request.url);
  const format = url.searchParams.get("format");
  if (format !== "xlsx" && format !== "pdf") {
    return NextResponse.json(
      { error: "format must be xlsx or pdf" },
      { status: 400 },
    );
  }

  const tab = parseExportTab(url.searchParams.get("tab"));
  const timeframe = timeframeForTab(tab);
  const signals = await getClosedOutcomeSignals(serviceRoleToken(), timeframe);

  if (signals.length === 0) {
    return NextResponse.json(
      { error: "No TP/SL-hit signals to export for this filter" },
      { status: 404 },
    );
  }

  const body =
    format === "xlsx"
      ? buildClosedSignalsXlsx(signals)
      : buildClosedSignalsPdf(signals, tab);
  const filename = exportFilename(format, tab);
  const contentType =
    format === "xlsx"
      ? "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
      : "application/pdf";

  return new NextResponse(new Uint8Array(body), {
    status: 200,
    headers: {
      "Content-Type": contentType,
      "Content-Disposition": `attachment; filename="${filename}"`,
      "Cache-Control": "no-store",
    },
  });
}
