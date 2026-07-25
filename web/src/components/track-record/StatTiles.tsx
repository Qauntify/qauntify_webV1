import type { Summary } from "@/lib/track-record";

export function StatTiles({ summary }: { summary: Summary }) {
  const tone = (n: number) => (n >= 0 ? "text-emerald-400" : "text-rose-400");
  const tiles = [
    { label: "Win rate", value: `${summary.winRate}%`, sub: `${summary.wins} / ${summary.total} closed`, cls: "text-emerald-400" },
    { label: "Net R", value: `${summary.netR >= 0 ? "+" : ""}${summary.netR}R`, sub: `across ${summary.total} trades`, cls: tone(summary.netR) },
    { label: "Avg / trade", value: `${summary.avgR >= 0 ? "+" : ""}${summary.avgR}R`, sub: "expectancy", cls: tone(summary.avgR) },
    { label: "Best streak", value: `${summary.bestStreak}`, sub: "wins in a row", cls: "text-ink" },
  ];
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
      {tiles.map((t) => (
        <div key={t.label} className="rounded-xl border border-line bg-card p-4">
          <div className="text-[10px] font-semibold uppercase tracking-wider text-slate/70">{t.label}</div>
          <div className={`mt-1 text-2xl font-extrabold ${t.cls}`}>{t.value}</div>
          <div className="mt-0.5 text-[11px] text-slate/70">{t.sub}</div>
        </div>
      ))}
    </div>
  );
}
