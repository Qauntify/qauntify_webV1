import type { Metadata } from "next";
import Link from "next/link";

import { DeleteSignalButton } from "@/components/admin/DeleteSignalButton";
import { ExportSignalsMenu } from "@/components/admin/ExportSignalsMenu";
import { SignalCard } from "@/components/dashboard/SignalsGrid";
import { Pagination } from "@/components/shared/Pagination";
import { requireAdminPage } from "@/lib/admin-guard";
import { getSignalsPaginated, getStats } from "@/lib/signals";
import { serviceRoleToken } from "@/lib/supabase/admin";

export const metadata: Metadata = {
  title: "Admin · Signals — Qauntify",
};

export const dynamic = "force-dynamic";

export default async function AdminSignals({
  searchParams,
}: {
  searchParams: Promise<{ tab?: string; page?: string }>;
}) {
  await requireAdminPage();
  const { tab, page: pageParam } = await searchParams;

  const currentTab = tab === "swing" ? "swing" : tab === "scalping" ? "scalping" : "all";
  const timeframe = currentTab === "swing" ? "1h" : currentTab === "scalping" ? "15m" : undefined;
  const page = Math.max(1, parseInt(pageParam ?? "1", 10) || 1);

  const token = serviceRoleToken();
  const [{ signals, total, totalPages, pageSize }, stats] = await Promise.all([
    getSignalsPaginated(page, token, timeframe),
    getStats(token, timeframe),
  ]);
  const exportableCount = stats.tpHits + stats.slHits;

  // Extra params to preserve the active tab when paginating
  const extraParams: Record<string, string> = currentTab !== "all" ? { tab: currentTab } : {};

  return (
    <>
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Signals</h1>
          <p className="mt-1 text-sm text-slate">
            Manage and view all stored signals. Export includes TP/SL hits only.
          </p>
        </div>
        <ExportSignalsMenu tab={currentTab} disabled={exportableCount === 0} />
      </div>

      <nav className="flex gap-2 border-b border-line pb-4 mb-6 overflow-x-auto">
        <Link
          href="/admin/signals"
          className={`nav-item ${currentTab === "all" ? "nav-item-active" : ""}`}
        >
          All
        </Link>
        <Link
          href="/admin/signals?tab=scalping"
          className={`nav-item ${currentTab === "scalping" ? "nav-item-active" : ""}`}
        >
          Scalping (15m)
        </Link>
        <Link
          href="/admin/signals?tab=swing"
          className={`nav-item ${currentTab === "swing" ? "nav-item-active" : ""}`}
        >
          Swing (1h)
        </Link>
      </nav>

      {signals.length > 0 ? (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
            {signals.map((s) => (
              <SignalCard
                key={s.id}
                signal={s}
                adminSlot={
                  <DeleteSignalButton
                    id={s.id}
                    triggerClassName="text-[10px] font-bold uppercase tracking-wider text-short hover:underline bg-short/10 px-2 py-1 rounded z-10 relative"
                  />
                }
              />
            ))}
          </div>
          <Pagination
            page={page}
            totalPages={totalPages}
            total={total}
            pageSize={pageSize}
            basePath="/admin/signals"
            extraParams={extraParams}
          />
        </>
      ) : (
        <p className="mt-8 text-sm text-slate">No signals found for this category.</p>
      )}
    </>
  );
}
