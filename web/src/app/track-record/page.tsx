import { Footer } from "@/components/shared/Footer";
import { Nav } from "@/components/shared/Nav";
import { MethodologyNote } from "@/components/track-record/MethodologyNote";
import { StatTiles } from "@/components/track-record/StatTiles";
import { TrackRecordTabs } from "@/components/track-record/TrackRecordTabs";
import { getTrackRecord } from "@/lib/track-record";
import { relativeTime } from "@/lib/relative-time";

export const revalidate = 60;

export const metadata = {
  title: "Live Track Record — Qauntify",
  description: "Every signal, wins and losses. Real, auto-updated performance.",
};

export default async function TrackRecordPage() {
  const tr = await getTrackRecord();
  const empty = tr.summary.total === 0;
  return (
    <>
      <Nav />
      <main className="flex-1">
        <section className="page-container py-10">
          <div className="mb-6 flex items-end justify-between gap-4">
            <div>
              <h1 className="text-2xl font-extrabold text-ink md:text-3xl">Live Track Record</h1>
              <p className="mt-1 text-sm text-slate/70">Every signal — wins and losses. Nothing cherry-picked.</p>
            </div>
            {tr.summary.updatedAt ? (
              <span className="whitespace-nowrap rounded-full border border-line px-3 py-1 text-[11px] text-slate/60">● updated {relativeTime(tr.summary.updatedAt)}</span>
            ) : null}
          </div>

          {empty ? (
            <div className="rounded-xl border border-line bg-card p-10 text-center text-slate/70">
              Your track record fills in as trades close. Check back soon.
            </div>
          ) : (
            <div className="space-y-4">
              <StatTiles summary={tr.summary} />
              <TrackRecordTabs
                equity={tr.equity}
                byStrategy={tr.byStrategy}
                bySymbol={tr.bySymbol}
                daily={tr.daily}
                recent={tr.recent}
              />
              <MethodologyNote />
            </div>
          )}
        </section>
      </main>
      <Footer />
    </>
  );
}
