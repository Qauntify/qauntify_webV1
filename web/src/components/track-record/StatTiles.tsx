import type { Summary } from "@/lib/track-record";

export function StatTiles({ summary }: { summary: Summary }) {
  const tone = (n: number) => (n >= 0 ? "text-emerald-400" : "text-rose-400");
  const signed = (n: number) => `${n >= 0 ? "+" : ""}${n}R`;
  // Net is the headline everywhere; gross sits underneath it so the cost drag
  // is legible rather than hidden.
  const tiles = [
    {
      label: "Net R",
      value: signed(summary.netR),
      sub: `${signed(summary.grossR)} before costs`,
      cls: tone(summary.netR),
    },
    {
      label: "Avg / trade",
      value: signed(summary.avgR),
      sub: "expectancy, net of costs",
      cls: tone(summary.avgR),
    },
    { label: "Best streak", value: `${summary.bestStreak}`, sub: "wins in a row", cls: "text-ink" },
    { label: "Closed trades", value: `${summary.total}`, sub: `${summary.wins}W / ${summary.losses}L`, cls: "text-ink" },
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
