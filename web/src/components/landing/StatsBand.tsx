import type { Stats } from "@/lib/signals";

export function StatsBand({ stats }: { stats: Stats }) {
  const items = [
    { value: stats.total, label: "Total signals" },
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
    <section className="section-block border-line bg-card/40 backdrop-blur-md">
      <div className="page-container grid grid-cols-1 divide-y divide-line py-2 sm:grid-cols-3 sm:divide-x sm:divide-y-0">
        {items.map((item, i) => (
          <div 
            key={item.label} 
            className="px-4 py-8 text-center sm:py-10 animate-fade-up"
            style={{ animationDelay: `${i * 150}ms` }}
          >
            <p
              className={`font-mono text-3xl font-bold ${
                item.tone === "long" ? "text-long" : "text-ink"
              }`}
            >
              {item.value}
            </p>
            <p className="mt-1.5 text-sm text-slate">{item.label}</p>
          </div>
        ))}
      </div>
    </section>
  );
}
