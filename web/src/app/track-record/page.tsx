import { Footer } from "@/components/shared/Footer";
import { Nav } from "@/components/shared/Nav";
import { TrackRecordTabs } from "@/components/track-record/TrackRecordTabs";
import { getDailyPnLStats } from "@/lib/signals";
import { serviceRoleToken } from "@/lib/supabase/admin";
import { getTrackRecord } from "@/lib/track-record";
import { relativeTime } from "@/lib/relative-time";

export const revalidate = 60;

export const metadata = {
  title: "Live Track Record — Qauntify",
  description: "Every signal, wins and losses. Real, auto-updated performance.",
};

export default async function TrackRecordPage() {
  const token = serviceRoleToken();
  const [tr, dailyPnL] = await Promise.all([
    getTrackRecord(),
    getDailyPnLStats(token, 365),
  ]);
  const empty = tr.summary.total === 0;
  return (
    <>
      <Nav />
      <main className="flex-1">
        <section className="page-container py-6 md:py-8">
          <div className="mb-5 flex items-end justify-between gap-4">
            <div>
              <h1 className="text-2xl font-extrabold text-ink md:text-3xl">Live Track Record</h1>
              <p className="mt-1 text-sm text-slate">Every signal — wins and losses. Nothing cherry-picked.</p>
            </div>
            {tr.summary.updatedAt ? (
              <span className="whitespace-nowrap rounded border border-line px-2.5 py-1 font-mono text-[11px] text-slate">
                updated {relativeTime(tr.summary.updatedAt)}
              </span>
            ) : null}
          </div>

          {empty ? (
            <div className="rounded-lg border border-line bg-card p-8 text-center text-sm text-slate">
              Your track record fills in as trades close. Check back soon.
            </div>
          ) : (
            <TrackRecordTabs
              byStrategy={tr.byStrategy}
              bySymbol={tr.bySymbol}
              daily={tr.daily}
              dailyPnL={dailyPnL}
              recent={tr.recent}
            />
          )}
        </section>
      </main>
      <Footer />
    </>
  );
}
