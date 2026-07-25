import type { DailyNet } from "@/lib/track-record";

export function Heatmap({ daily }: { daily: DailyNet[] }) {
  const recent = daily.slice(-91);
  if (recent.length === 0) return <div className="text-sm text-slate/60">No closed days yet.</div>;
  return (
    <div className="flex flex-wrap gap-[3px]">
      {recent.map((d) => {
        const color = d.net > 0 ? "bg-emerald-400" : d.net < 0 ? "bg-rose-400" : "bg-slate/20";
        const opacity = d.net === 0 ? 0.4 : Math.min(1, 0.4 + Math.abs(d.net) / 4);
        return (
          <div
            key={d.date}
            title={`${d.date}: ${d.net >= 0 ? "+" : ""}${d.net}R`}
            className={`h-3.5 w-3.5 rounded-[3px] ${color}`}
            style={{ opacity }}
          />
        );
      })}
    </div>
  );
}
