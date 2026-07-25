import type { BreakdownRow } from "@/lib/track-record";

export function Breakdown({ title, rows }: { title: string; rows: BreakdownRow[] }) {
  return (
    <div className="rounded-xl border border-line bg-card p-4">
      <div className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-slate/70">{title}</div>
      {rows.length === 0 ? (
        <div className="text-sm text-slate/60">No data yet.</div>
      ) : (
        rows.map((r) => (
          <div key={r.name} className="mb-2.5">
            <div className="mb-1 flex justify-between text-xs">
              <span className="text-ink">{r.name}</span>
              <span className="text-slate/70">
                {r.winRate}% · <b className={r.netR >= 0 ? "text-emerald-400" : "text-rose-400"}>{r.netR >= 0 ? "+" : ""}{r.netR}R</b>
              </span>
            </div>
            <div className="h-1.5 overflow-hidden rounded bg-slate/15">
              <div className={`h-full ${r.winRate >= 50 ? "bg-emerald-400" : "bg-rose-400"}`} style={{ width: `${r.winRate}%` }} />
            </div>
          </div>
        ))
      )}
    </div>
  );
}
