import Link from "next/link";
import { redirect } from "next/navigation";

import { DashboardShell } from "@/components/dashboard/DashboardShell";
import { SignalsGrid } from "@/components/dashboard/SignalsGrid";
import { StatsBar } from "@/components/dashboard/StatsBar";
import { Notice } from "@/components/shared/Notice";
import { getSignals, getStats } from "@/lib/signals";
import { createClient } from "@/lib/supabase/server";

export const metadata = {
  title: "Dashboard — Qauntify",
};

export const revalidate = 30;

const SESSIONS = [
  {
    title: "Scalping",
    subtitle: "15m chart — fast, frequent setups",
    timeframe: "15m",
    emptyHint: "Scalp setups are checked every ~10 minutes on the 15m chart.",
  },
  {
    title: "Swing",
    subtitle: "1h chart — slower, higher-conviction setups",
    timeframe: "1h",
    emptyHint: "Swing setups are checked every ~10 minutes on the 1h chart.",
  },
] as const;

async function SessionSection({
  title,
  subtitle,
  timeframe,
  emptyHint,
  accessToken,
}: {
  title: string;
  subtitle: string;
  timeframe: string;
  emptyHint: string;
  accessToken: string | undefined;
}) {
  const [signals, stats] = await Promise.all([
    getSignals(30, accessToken, timeframe),
    getStats(accessToken, timeframe),
  ]);

  return (
    <section>
      <div className="mb-3 flex items-baseline justify-between">
        <div>
          <h2 className="text-base font-semibold text-ink">{title}</h2>
          <p className="text-xs text-slate">{subtitle}</p>
        </div>
        {signals.length > 0 ? (
          <span className="font-mono text-xs text-slate">
            {signals.length} signal{signals.length === 1 ? "" : "s"}
          </span>
        ) : null}
      </div>

      <StatsBar stats={stats} />

      {signals.length > 0 ? (
        <div className="mt-4">
          <SignalsGrid signals={signals} />
        </div>
      ) : (
        <div className="mt-4 rounded-lg border border-dashed border-line bg-card p-10 text-center">
          <p className="text-sm font-semibold">No {title.toLowerCase()} signals yet</p>
          <p className="mx-auto mt-1 max-w-sm text-xs text-slate">{emptyHint}</p>
        </div>
      )}
    </section>
  );
}

export default async function Dashboard({
  searchParams,
}: {
  searchParams: Promise<{ admin?: string; tab?: string }>;
}) {
  const supabase = await createClient();
  // getUser() re-verifies the token with the auth server — the redirect
  // decision must not trust a raw (possibly stale/tampered) cookie
  // session. getSession() is only safe to read afterward, purely to pull
  // out the access token for the RLS-authenticated signals fetches below.
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");
  const { data: { session } } = await supabase.auth.getSession();
  const accessToken = session?.access_token;
  const { admin, tab } = await searchParams;
  
  const currentTab = tab === "swing" ? "swing" : tab === "scalping" ? "scalping" : "all";

  return (
    <DashboardShell
      title="Signals"
      subtitle="AI-confirmed setups — refreshed every engine run"
    >
      <div className="w-full space-y-6">
        {admin === "denied" ? (
          <Notice tone="error">
            Admin access is not enabled for {user.email}. Ask the
            owner to add your email to ADMIN_EMAILS, then sign out and back in.
          </Notice>
        ) : null}

        <div className="lg:hidden">
          <h1 className="text-xl font-bold">Signals</h1>
          <p className="text-sm text-slate">
            AI-confirmed setups — refreshed every engine run
          </p>
        </div>

        <nav className="flex gap-2 border-b border-line pb-4 overflow-x-auto">
          <Link
            href="/dashboard?tab=all"
            className={`nav-item ${currentTab === "all" ? "nav-item-active" : ""}`}
          >
            All
          </Link>
          <Link
            href="/dashboard?tab=scalping"
            className={`nav-item ${currentTab === "scalping" ? "nav-item-active" : ""}`}
          >
            Scalping (15m)
          </Link>
          <Link
            href="/dashboard?tab=swing"
            className={`nav-item ${currentTab === "swing" ? "nav-item-active" : ""}`}
          >
            Swing (1h)
          </Link>
        </nav>

        {currentTab === "all" ? (
          SESSIONS.map((s) => (
            <SessionSection key={s.timeframe} accessToken={accessToken} {...s} />
          ))
        ) : (
          <SessionSection 
            accessToken={accessToken} 
            {...SESSIONS.find((s) => s.title.toLowerCase() === currentTab)!} 
          />
        )}
      </div>
    </DashboardShell>
  );
}
