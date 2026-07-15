import Link from "next/link";
import { redirect } from "next/navigation";

import { DashboardShell } from "@/components/dashboard/DashboardShell";
import { SignalsGrid } from "@/components/dashboard/SignalsGrid";
import { StatsBar } from "@/components/dashboard/StatsBar";
import { TradingFloor } from "@/components/floor/TradingFloor";
import { Notice } from "@/components/shared/Notice";
import { getSignals, getStats } from "@/lib/signals";
import { createClient } from "@/lib/supabase/server";

export const metadata = {
  title: "Dashboard — Qauntify",
};

export const revalidate = 30;

const SESSIONS = [
  {
    id: "super-scalping",
    title: "Super scalping",
    subtitle: "5m ICT — sweep, CHoCH, FVG retest (tight SL/TP)",
    timeframe: "5m",
    emptyHint: "Super-scalp setups are checked every ~10 minutes on the 5m chart.",
  },
  {
    id: "scalping",
    title: "Scalping",
    subtitle: "15m chart — CE + LWMA zone setups",
    timeframe: "15m",
    emptyHint: "Scalp setups are checked every ~10 minutes on the 15m chart.",
  },
  {
    id: "swing",
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
  id?: string;
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
  
  const currentTab =
    tab === "floor"
      ? "floor"
      : tab === "swing"
        ? "swing"
        : tab === "scalping"
          ? "scalping"
          : tab === "super-scalping"
            ? "super-scalping"
            : "all";
  const isFloor = currentTab === "floor";
  const title = isFloor ? "Trading Floor" : "Signals";
  const subtitle = isFloor
    ? "Desk board and PM chat"
    : "AI-confirmed setups — refreshed every engine run";

  return (
    <DashboardShell
      title={title}
      subtitle={subtitle}
    >
      <div className="w-full space-y-6">
        {admin === "denied" ? (
          <Notice tone="error">
            Admin access is not enabled for {user.email}. Ask the
            owner to add your email to ADMIN_EMAILS, then sign out and back in.
          </Notice>
        ) : null}

        <div className="lg:hidden">
          <h1 className="text-xl font-bold">{title}</h1>
          <p className="text-sm text-slate">
            {subtitle}
          </p>
        </div>

        <nav className="flex gap-2 border-b border-line pb-4 overflow-x-auto relative">
          <Link
            href="/dashboard?tab=all"
            className={`rounded-full px-4 py-2 text-sm font-medium transition-all duration-200 ${
              currentTab === "all"
                ? "bg-ink text-paper shadow-md"
                : "text-slate hover:bg-card hover:text-ink"
            }`}
          >
            All
          </Link>
          <Link
            href="/dashboard?tab=super-scalping"
            className={`rounded-full px-4 py-2 text-sm font-medium transition-all duration-200 ${
              currentTab === "super-scalping"
                ? "bg-ink text-paper shadow-md"
                : "text-slate hover:bg-card hover:text-ink"
            }`}
          >
            Super scalp (5m)
          </Link>
          <Link
            href="/dashboard?tab=scalping"
            className={`rounded-full px-4 py-2 text-sm font-medium transition-all duration-200 ${
              currentTab === "scalping"
                ? "bg-ink text-paper shadow-md"
                : "text-slate hover:bg-card hover:text-ink"
            }`}
          >
            Scalping (15m)
          </Link>
          <Link
            href="/dashboard?tab=swing"
            className={`rounded-full px-4 py-2 text-sm font-medium transition-all duration-200 ${
              currentTab === "swing"
                ? "bg-ink text-paper shadow-md"
                : "text-slate hover:bg-card hover:text-ink"
            }`}
          >
            Swing (1h)
          </Link>
          <Link
            href="/dashboard?tab=floor"
            className={`rounded-full px-4 py-2 text-sm font-medium transition-all duration-200 ${
              currentTab === "floor"
                ? "bg-ink text-paper shadow-md"
                : "text-slate hover:bg-card hover:text-ink"
            }`}
          >
            Trading Floor
          </Link>
        </nav>

        {currentTab === "floor" ? (
          <TradingFloor />
        ) : currentTab === "all" ? (
          SESSIONS.map((s) => (
            <SessionSection key={s.timeframe} accessToken={accessToken} {...s} />
          ))
        ) : (
          <SessionSection
            accessToken={accessToken}
            {...SESSIONS.find((s) => s.id === currentTab)!}
          />
        )}
      </div>
    </DashboardShell>
  );
}
