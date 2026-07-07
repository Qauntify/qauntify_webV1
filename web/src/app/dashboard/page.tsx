import type { Metadata } from "next";
import Link from "next/link";

import { StatsBar } from "@/components/dashboard/StatsBar";
import { Footer } from "@/components/shared/Footer";
import { Nav } from "@/components/shared/Nav";
import { TradeTicket } from "@/components/shared/TradeTicket";
import { getSignals, getStats } from "@/lib/signals";
import { createClient } from "@/lib/supabase/server";

export const metadata: Metadata = {
  title: "Dashboard — FinhubKH",
};

// Signals change whenever the engine runs — read the DB on every request.
export const dynamic = "force-dynamic";

export default async function Dashboard() {
  const supabase = await createClient();
  const { data } = await supabase.auth.getSession();
  const accessToken = data.session?.access_token;

  const signals = await getSignals(50, accessToken);
  const stats = await getStats(accessToken);
  return (
    <>
      <Nav />
      <main className="flex-1">
        <div className="mx-auto max-w-3xl px-6 py-12">
          <h1 className="font-display text-4xl tracking-tight">Signals</h1>
          <p className="mt-2 text-sm text-slate">
            Every AI-confirmed setup, newest first. Refresh after an engine run
            to see new entries.
          </p>
          {!accessToken ? (
            <div className="mt-6 flex flex-col gap-3 rounded-xl border border-line bg-card p-5 sm:flex-row sm:items-center sm:justify-between">
              <p className="text-sm text-slate">
                <span className="font-medium text-ink">Preview mode.</span>{" "}
                You&apos;re seeing the last 24 hours only — create a free
                account to unlock the full signal history.
              </p>
              <div className="flex shrink-0 items-center gap-3">
                <Link
                  href="/login"
                  className="text-sm text-slate hover:text-ink"
                >
                  Sign in
                </Link>
                <Link
                  href="/signup"
                  className="rounded-lg bg-ink px-4 py-2 text-sm font-medium text-paper hover:bg-ink/85"
                >
                  Sign up free
                </Link>
              </div>
            </div>
          ) : null}
          <div className="mt-8">
            <StatsBar stats={stats} />
          </div>
          {signals.length > 0 ? (
            <div className="mt-8 flex flex-col gap-5">
              {signals.map((s) => (
                <TradeTicket key={s.id} signal={s} />
              ))}
            </div>
          ) : (
            <div className="mt-8 rounded-xl border border-dashed border-line p-12 text-center">
              <p className="font-display text-xl">No signals yet</p>
              <p className="mx-auto mt-2 max-w-sm text-sm leading-relaxed text-slate">
                Run the engine to scan the markets:{" "}
                <code className="rounded bg-line px-1.5 py-0.5 font-mono text-xs">
                  python -m signals.run
                </code>{" "}
                — confirmed setups appear here. A quiet dashboard is normal;
                crossovers are infrequent by design.
              </p>
            </div>
          )}
        </div>
      </main>
      <Footer />
    </>
  );
}
