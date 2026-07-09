import type { Metadata } from "next";

import { DailyPnLCalendar } from "@/components/admin/DailyPnLCalendar";
import { requireAdminPage } from "@/lib/admin-guard";
import { getDailyPnLStats, getStats } from "@/lib/signals";
import { getEngineStatus, listUsers, serviceRoleToken } from "@/lib/supabase/admin";

export const metadata: Metadata = {
  title: "Admin · Overview — Qauntify",
};

export const dynamic = "force-dynamic";

export default async function AdminOverview() {
  await requireAdminPage();

  const token = serviceRoleToken();
  const [users, stats, engineStatus, pnlData] = await Promise.all([
    listUsers(),
    getStats(token),
    getEngineStatus(),
    getDailyPnLStats(token, 365),
  ]);

  const engine = engineStatus
    ? {
        label: engineStatus.isHealthy ? "Healthy" : "Stale",
        detail: `Last run ${engineStatus.ageMinutes} min ago.`,
      }
    : { label: "Unknown", detail: "No heartbeat yet." };

  const tiles = [
    { label: "Users", value: users ? String(users.length) : "—" },
    { label: "Signals", value: String(stats.total) },
    {
      label: "Avg confidence",
      value: stats.total > 0 ? String(stats.avgConfidence) : "—",
    },
    { label: "Long / short", value: `${stats.longs}L / ${stats.shorts}S` },
    {
      label: "Win rate",
      value: stats.winRate !== null ? `${stats.winRate}%` : "—",
      sub:
        stats.winRate !== null
          ? `${stats.tpHits} TP hit / ${stats.slHits} SL hit`
          : "No closed signals yet.",
    },
    { label: "Engine", value: engine.label, sub: engine.detail },
  ];

  return (
    <>
      <h1 className="text-2xl font-bold">Overview</h1>
      <p className="mt-1 text-sm text-slate">
        Engine health and member stats.
      </p>
      <div className="mt-8 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {tiles.map((tile) => (
          <div key={tile.label} className="stat-tile">
            <p className="stat-tile-label">{tile.label}</p>
            <p className="stat-tile-value">{tile.value}</p>
            {"sub" in tile && tile.sub ? (
              <p className="mt-2 text-xs text-slate">{tile.sub}</p>
            ) : null}
          </div>
        ))}
      </div>
      
      <DailyPnLCalendar data={pnlData} />
    </>
  );
}
