import type { Metadata } from "next";
import { redirect } from "next/navigation";

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
  if (!data.session) redirect("/login");
  const accessToken = data.session.access_token;

  const signals = await getSignals(50, accessToken);
  const stats = await getStats(accessToken);
  return (
    <>
      <Nav />
      <main className="flex-1">
        <div className="mx-auto max-w-3xl px-6 py-12">
          <h1 className="font-display text-3xl tracking-tight">Signals</h1>
          <p className="mt-2 text-sm text-slate">
            Every AI-confirmed setup, newest first. Refresh after an engine run
            to see new entries.
          </p>
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
                The engine scans the markets every 10 minutes and only stores
                setups the AI confirms. A quiet dashboard is normal — good
                setups are rare by design.
              </p>
            </div>
          )}
        </div>
      </main>
      <Footer />
    </>
  );
}
