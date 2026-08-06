import { dispatchHealthcheckWorkflow } from "@/lib/github-engine";
import { handleCronDispatch } from "@/lib/cron-dispatch";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  return handleCronDispatch(
    request,
    dispatchHealthcheckWorkflow,
    "session-healthcheck",
  );
}

export async function POST(request: Request) {
  return GET(request);
}
