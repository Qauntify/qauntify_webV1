import type { Stats } from "@/lib/signals";

export function StatsBar({ stats }: { stats: Stats }) {
  const items = [
    { label: "Total signals", value: String(stats.total) },
    {
      label: "Avg confidence",
      value: stats.total > 0 ? `${stats.avgConfidence}%` : "—",
    },
    { label: "Long / short", value: `${stats.longs}L / ${stats.shorts}S` },
    {
      label: "Win rate",
      value:
        stats.winRate !== null
          ? `${stats.winRate}%`
          : "—",
      detail:
        stats.winRate !== null
          ? `${stats.tpHits}W / ${stats.slHits}L`
          : undefined,
    },
  ];

  return (
    <div className="grid w-full gap-px overflow-hidden rounded-lg border border-line bg-line sm:grid-cols-2 lg:grid-cols-4">
      {items.map((item) => (
        <div key={item.label} className="bg-card px-5 py-4">
          <p className="text-xs font-medium uppercase tracking-wide text-slate">
            {item.label}
          </p>
          <p className="mt-1 font-mono text-2xl font-bold tabular-nums text-ink">
            {item.value}
          </p>
          {item.detail ? (
            <p className="mt-0.5 text-xs text-slate">{item.detail}</p>
          ) : null}
        </div>
      ))}
    </div>
  );
}
