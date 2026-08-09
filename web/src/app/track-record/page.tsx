import { Footer } from "@/components/shared/Footer";
import { Nav } from "@/components/shared/Nav";
import { TrackRecordTabs } from "@/components/track-record/TrackRecordTabs";
import { getDailyPnLStats } from "@/lib/signals";
import { serviceRoleToken } from "@/lib/supabase/admin";
import { getTrackRecord } from "@/lib/track-record";
import { relativeTime } from "@/lib/relative-time";

export const revalidate = 60;

export const metadata = {
  title: "កំណត់ត្រាលទ្ធផល — Qauntify",
  description: "គ្រប់ signals ឈ្នះនិងចាញ់។ លទ្ធផលពិត ធ្វើបច្ចុប្បន្នភាពស្វ័យប្រវត្តិ។",
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
                កំណត់ត្រាលទ្ធផល
              </h1>
              <p className="mt-2 max-w-2xl text-base text-slate">
                គ្រប់ signals ដែលបានបិទ — ឈ្នះនិងចាញ់។ គ្មានការជ្រើសរើសលទ្ធផលល្អតែមួយ។
              </p>
            </div>
            {tr.summary.updatedAt ? (
              <p className="text-sm text-slate">
                ធ្វើបច្ចុប្បន្នភាព {relativeTime(tr.summary.updatedAt)}
              </p>
            ) : null}
          </div>

          {empty ? (
            <div className="rounded-xl border border-dashed border-line bg-card px-6 py-14 text-center">
              <p className="text-sm font-semibold text-ink">មិនទាន់មានការជួញដូរបិទទេ</p>
              <p className="mx-auto mt-1.5 max-w-sm text-sm text-slate">
                កំណត់ត្រាលទ្ធផលនឹងបំពេញនៅពេលការជួញដូរបិទ។ សូមត្រឡប់មកម្តងទៀតឆាប់ៗ។
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
