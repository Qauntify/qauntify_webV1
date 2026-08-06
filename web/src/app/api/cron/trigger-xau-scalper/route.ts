import { dispatchXauScalperRestart } from "@/lib/github-engine";
import { handleCronDispatch } from "@/lib/cron-dispatch";

export const dynamic = "force-dynamic";

/** Unconditional XAU scalper start/restart for cron-job.org (hourly). */
export async function GET(request: Request) {
  return handleCronDispatch(request, dispatchXauScalperRestart, "xau-scalper");
}

export async function POST(request: Request) {
  return GET(request);
}
