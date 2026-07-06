import type { Stats } from "@/lib/signals";

export function StatsBar({ stats }: { stats: Stats }) {
  const items = [
    { label: "Signals", value: String(stats.total) },
    {
      label: "Avg confidence",
      value: stats.total > 0 ? String(stats.avgConfidence) : "—",
    },
    { label: "Long / short", value: `${stats.longs}L / ${stats.shorts}S` },
  ];
  return (
    <div className="grid gap-4 sm:grid-cols-3">
      {items.map((item) => (
        <div
          key={item.label}
          className="rounded-xl border border-line bg-white px-5 py-4"
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
