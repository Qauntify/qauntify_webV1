import type { Stats } from "@/lib/signals";

export function StatsBand({ stats }: { stats: Stats }) {
  const items = [
    { value: stats.total, label: "signals generated" },
    {
      value: stats.total > 0 ? stats.avgConfidence : "—",
      label: "average confidence",
    },
    { value: 2, label: "markets covered" },
  ];
  return (
    <section className="border-b border-line bg-white">
      <div className="mx-auto grid max-w-6xl grid-cols-1 divide-y divide-line px-6 sm:grid-cols-3 sm:divide-x sm:divide-y-0">
        {items.map((item) => (
          <div key={item.label} className="py-8 text-center">
            <p className="font-mono text-3xl font-semibold">{item.value}</p>
            <p className="mt-1 text-sm text-slate">{item.label}</p>
          </div>
        ))}
      </div>
      <p className="border-t border-line py-3 text-center text-xs text-slate">
        Live numbers from our own engine — built in public, no invented stats.
      </p>
    </section>
  );
}
