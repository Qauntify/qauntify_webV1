import type { Metadata } from "next";

import { TradeTicket } from "@/components/shared/TradeTicket";
import { requireAdminPage } from "@/lib/admin-guard";
import { getSignals, getStats } from "@/lib/signals";
import { getEngineStatus, listUsers, serviceRoleToken } from "@/lib/supabase/admin";

export const metadata: Metadata = {
  title: "Admin · Overview — FinhubKH",
};

export const dynamic = "force-dynamic";

export default async function AdminOverview() {
  await requireAdminPage();

  const token = serviceRoleToken();
  const [users, stats, signals, engineStatus] = await Promise.all([
    listUsers(),
    getStats(token),
    getSignals(5, token),
    getEngineStatus(),
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
        Engine health, member stats, and latest signals.
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
      <h2 className="mt-12 text-xl font-bold">Latest signals</h2>
      {signals.length > 0 ? (
        <div className="mt-4 flex max-w-3xl flex-col gap-5">
          {signals.map((s) => (
            <TradeTicket key={s.id} signal={s} />
          ))}
        </div>
      ) : (
        <p className="mt-4 text-sm text-slate">
          Nothing stored yet — the engine scans every 10 minutes, and
          confirmed setups land here.
        </p>
      )}
    </>
  );
}
