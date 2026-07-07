import { redirect } from "next/navigation";

import { DashboardShell } from "@/components/dashboard/DashboardShell";
import { SignalsGrid } from "@/components/dashboard/SignalsGrid";
import { StatsBar } from "@/components/dashboard/StatsBar";
import { Notice } from "@/components/shared/Notice";
import { getSignals, getStats } from "@/lib/signals";
import { createClient } from "@/lib/supabase/server";

export const metadata = {
  title: "Dashboard — FinhubKH",
};

export const dynamic = "force-dynamic";

export default async function Dashboard({
  searchParams,
}: {
  searchParams: Promise<{ admin?: string }>;
}) {
  const supabase = await createClient();
  const { data } = await supabase.auth.getSession();
  if (!data.session) redirect("/login");
  const accessToken = data.session.access_token;
  const { admin } = await searchParams;

  const signals = await getSignals(50, accessToken);
  const stats = await getStats(accessToken);

  return (
    <DashboardShell
      title="Signals"
      subtitle="AI-confirmed setups — refreshed every engine run"
    >
      <div className="w-full space-y-6">
        {admin === "denied" ? (
          <Notice tone="error">
            Admin access is not enabled for {data.session.user.email}. Ask the
            owner to add your email to ADMIN_EMAILS, then sign out and back in.
          </Notice>
        ) : null}

        <div className="lg:hidden">
          <h1 className="text-xl font-bold">Signals</h1>
          <p className="text-sm text-slate">
            AI-confirmed setups — refreshed every engine run
          </p>
        </div>

        <StatsBar stats={stats} />

        {signals.length > 0 ? (
          <div>
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-sm font-semibold text-ink">
                Trade log
                <span className="ml-2 font-normal text-slate">
                  ({signals.length} signal{signals.length === 1 ? "" : "s"})
                </span>
              </h2>
            </div>
            <SignalsGrid signals={signals} />
          </div>
        ) : (
          <div className="rounded-lg border border-dashed border-line bg-card p-16 text-center">
            <p className="text-lg font-semibold">No signals yet</p>
            <p className="mx-auto mt-2 max-w-md text-sm text-slate">
              The engine scans every 10 minutes. A quiet dashboard is normal —
              good setups are rare by design.
            </p>
          </div>
        )}
      </div>
    </DashboardShell>
  );
}
