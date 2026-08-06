import { Footer } from "@/components/shared/Footer";
import { Nav } from "@/components/shared/Nav";
import { TrackRecordTabs } from "@/components/track-record/TrackRecordTabs";
import { getDailyPnLStats } from "@/lib/signals";
import { serviceRoleToken } from "@/lib/supabase/admin";
import { getTrackRecord } from "@/lib/track-record";
import { relativeTime } from "@/lib/relative-time";

export const revalidate = 60;

export const metadata = {
  title: "Track Record — Qauntify",
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
      <main className="flex min-h-[calc(100svh-4rem)] flex-1 flex-col bg-paper">
        <div className="w-full flex-1 px-4 py-8 sm:px-6 lg:px-8 xl:px-10">
          <div className="mb-8 flex flex-wrap items-end justify-between gap-3">
            <div>
              <h1 className="text-3xl font-bold tracking-tight text-ink md:text-4xl">
                Track Record
              </h1>
              <p className="mt-2 max-w-2xl text-base text-slate">
                Every closed signal — wins and losses. Nothing cherry-picked.
              </p>
            </div>
            {tr.summary.updatedAt ? (
              <p className="text-sm text-slate">
                Updated {relativeTime(tr.summary.updatedAt)}
              </p>
            ) : null}
          </div>

          {empty ? (
            <div className="rounded-xl border border-dashed border-line bg-card px-6 py-14 text-center">
              <p className="text-sm font-semibold text-ink">No closed trades yet</p>
              <p className="mx-auto mt-1.5 max-w-sm text-sm text-slate">
                Your track record fills in as trades close. Check back soon.
              </p>
            </div>
          ) : (
            <TrackRecordTabs
              byStrategy={tr.byStrategy}
              bySymbol={tr.bySymbol}
              dailyPnL={dailyPnL}
              recent={tr.recent}
            />
          )}
        </div>
      </main>
      <Footer />
    </>
  );
}
