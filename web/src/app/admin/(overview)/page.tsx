import type { Metadata } from "next";

import { requireAdminPage } from "@/lib/admin-guard";
import { getStats } from "@/lib/signals";
import {
  getEngineStatus,
  getXauScanStatus,
  listUsers,
  serviceRoleToken,
} from "@/lib/supabase/admin";

export const metadata: Metadata = {
  title: "Admin · Overview — Qauntify",
};

export const revalidate = 30;

export default async function AdminOverview() {
  await requireAdminPage();

  const token = serviceRoleToken();
  const [users, stats, engineStatus, xauScanStatus] = await Promise.all([
    listUsers(),
    getStats(token),
    getEngineStatus(),
    getXauScanStatus(),
  ]);

  const engine = engineStatus
    ? {
        label: engineStatus.isHealthy ? "Healthy" : "Stale",
        detail: `Last run ${engineStatus.ageMinutes} min ago.`,
      }
    : { label: "Unknown", detail: "No heartbeat yet." };

  const xauScalper = xauScanStatus
    ? {
        label: xauScanStatus.isHealthy ? "Healthy" : "Stale",
        detail: `Last scan ${xauScanStatus.ageMinutes} min ago.`,
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
          ? `${stats.tpHits} full / ${stats.partialWins} LLM partial / ${stats.slHits} SL`
          : "No closed LLM signals yet.",
    },
    { label: "Engine", value: engine.label, sub: engine.detail },
    { label: "XAU Scalper", value: xauScalper.label, sub: xauScalper.detail },
  ];

  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
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
  );
}
