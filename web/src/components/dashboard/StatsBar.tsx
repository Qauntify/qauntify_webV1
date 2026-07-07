import type { Stats } from "@/lib/signals";

export function StatsBar({ stats }: { stats: Stats }) {
  const items = [
    { label: "Signals", value: String(stats.total) },
    {
      label: "Avg confidence",
      value: stats.total > 0 ? String(stats.avgConfidence) : "—",
    },
    { label: "Long / short", value: `${stats.longs}L / ${stats.shorts}S` },
    {
      label: "Win rate",
      value:
        stats.winRate !== null
          ? `${stats.winRate}% (${stats.tpHits}W/${stats.slHits}L)`
          : "—",
    },
  ];
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {items.map((item) => (
        <div
          key={item.label}
          className="rounded-xl border border-line bg-card px-5 py-4"
        >
          <p className="text-xs uppercase tracking-wider text-slate">
            {item.label}
          </p>
          <p className="mt-1 font-mono text-2xl font-semibold">{item.value}</p>
        </div>
      ))}
    </div>
  );
}
