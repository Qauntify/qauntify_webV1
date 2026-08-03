import type { Metadata } from "next";
import Link from "next/link";

import { DeleteSignalButton } from "@/components/admin/DeleteSignalButton";
import { ExportSignalsMenu } from "@/components/admin/ExportSignalsMenu";
import { SignalCard } from "@/components/dashboard/SignalsGrid";
import { Pagination } from "@/components/shared/Pagination";
import { requireAdminPage } from "@/lib/admin-guard";
import {
  getSignalsPaginated,
  getStats,
  getWarRoomSignalsPaginated,
} from "@/lib/signals";
import { serviceRoleToken } from "@/lib/supabase/admin";

export const metadata: Metadata = {
  title: "Admin · Signals — Qauntify",
};

export const revalidate = 30;

type SignalsTab =
  | "all"
  | "llm"
  | "war-room"
  | "super-scalping"
  | "scalping"
  | "swing";

function parseTab(tab: string | undefined): SignalsTab {
  if (tab === "llm") return "llm";
  if (tab === "war-room") return "war-room";
  if (tab === "swing") return "swing";
  if (tab === "scalping") return "scalping";
  if (tab === "super-scalping") return "super-scalping";
  return "all";
}

export default async function AdminSignals({
  searchParams,
}: {
  searchParams: Promise<{ tab?: string; page?: string }>;
}) {
  await requireAdminPage();
  const { tab, page: pageParam } = await searchParams;

  const currentTab = parseTab(tab);
  const timeframe =
    currentTab === "swing"
      ? "1h"
      : currentTab === "scalping"
        ? "15m"
        : currentTab === "super-scalping"
          ? "5m"
          : undefined;
  const page = Math.max(1, parseInt(pageParam ?? "1", 10) || 1);
  const isLlmTab = currentTab === "llm";
  const isWarRoomTab = currentTab === "war-room";

  const token = serviceRoleToken();
  const [pageData, stats] = await Promise.all([
    isWarRoomTab
      ? getWarRoomSignalsPaginated(page, token)
      : getSignalsPaginated(page, token, timeframe),
    getStats(token, timeframe),
  ]);
  const { signals, total, totalPages, pageSize } = pageData;
  const exportableCount = stats.tpHits + stats.partialWins + stats.slHits;

  const extraParams: Record<string, string> =
    currentTab !== "all" ? { tab: currentTab } : {};

  const exportTab =
    currentTab === "llm" || currentTab === "war-room" ? "all" : currentTab;

  const title = isWarRoomTab
    ? "War Room Signals"
    : isLlmTab
      ? "LLM Signals"
      : "Signals";
  const subtitle = isWarRoomTab
    ? "Signal cards that have an AI War Room debate on file — same cards as the main list."
    : isLlmTab
      ? "Every signal SEA-LION confirmed and stored. Same cards as the main list, scoped to LLM-approved setups."
      : "Manage and view all stored signals. Export includes TP/SL hits only.";

  return (
    <>
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">{title}</h1>
          <p className="mt-1 text-sm text-slate">{subtitle}</p>
        </div>
        <ExportSignalsMenu tab={exportTab} disabled={exportableCount === 0} />
      </div>

      <nav className="mb-6 flex gap-2 overflow-x-auto border-b border-line pb-4">
        <Link
          href="/admin/signals"
          className={`nav-item ${currentTab === "all" ? "nav-item-active" : ""}`}
        >
          All
        </Link>
        <Link
          href="/admin/signals?tab=llm"
          className={`nav-item ${isLlmTab ? "nav-item-active" : ""}`}
        >
          LLM
        </Link>
        <Link
          href="/admin/signals?tab=war-room"
          className={`nav-item ${isWarRoomTab ? "nav-item-active" : ""}`}
        >
          War Room
        </Link>
        <Link
          href="/admin/signals?tab=super-scalping"
          className={`nav-item ${currentTab === "super-scalping" ? "nav-item-active" : ""}`}
        >
          Super scalp (5m)
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

      {isLlmTab || isWarRoomTab ? (
        <div className="mb-5 rounded-lg border border-accent/20 bg-accent-soft/40 px-4 py-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-accent">
            {isWarRoomTab ? "War Room" : "LLM Signal"}
          </p>
          <p className="mt-1 text-sm text-slate">
            {isWarRoomTab
              ? `Showing ${total} signal${total === 1 ? "" : "s"} with a War Room debate.`
              : `Showing ${total} SEA-LION-confirmed signal${total === 1 ? "" : "s"} across every timeframe.`}
          </p>
        </div>
      ) : null}

      {signals.length > 0 ? (
        <>
          <div className="grid grid-cols-1 gap-5 md:grid-cols-2 lg:grid-cols-3">
            {signals.map((s) => (
              <SignalCard
                key={s.id}
                signal={s}
                showLlmBadge={isLlmTab}
                showWarRoomBadge={isWarRoomTab}
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
        <p className="mt-8 text-sm text-slate">
          {isWarRoomTab
            ? "No War Room signals yet."
            : isLlmTab
              ? "No LLM-confirmed signals yet."
              : "No signals found for this category."}
        </p>
      )}
    </>
  );
}
