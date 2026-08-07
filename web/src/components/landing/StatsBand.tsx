import type { Stats } from "@/lib/signals";

/** Kept for reuse; homepage stats live inside Hero. */
export function StatsBand({ stats }: { stats: Stats }) {
  const items = [
    { value: stats.total, label: "Signals logged" },
    {
      value: stats.total > 0 ? `${stats.avgConfidence}%` : "—",
      label: "Avg confidence",
    },
    {
      value: stats.winRate !== null ? `${stats.winRate}%` : "—",
      label: "Win rate",
      tone: stats.winRate !== null && stats.winRate >= 50 ? "long" : undefined,
    },
  ];
  return (
    <section className="border-b border-line bg-paper">
      <div className="page-container grid grid-cols-3 divide-x divide-line">
        {items.map((item) => (
          <div key={item.label} className="px-3 py-4 text-center sm:px-6 sm:py-5">
            <p
              className={`font-mono text-xl font-bold tracking-tight sm:text-2xl ${
                item.tone === "long" ? "text-long" : "text-ink"
              }`}
            >
              {item.value}
            </p>
            <p className="mt-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate sm:text-[11px]">
              {item.label}
            </p>
          </div>
        ))}
      </div>
    </section>
  );
}
