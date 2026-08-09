import type { BreakdownRow } from "@/lib/track-record";

export function Breakdown({ title, rows }: { title: string; rows: BreakdownRow[] }) {
  return (
    <div className="rounded-xl border border-line bg-card p-5">
      <h3 className="text-sm font-semibold text-ink">{title}</h3>
      {rows.length === 0 ? (
        <p className="mt-4 text-sm text-slate">មិនទាន់មានទិន្នន័យទេ។</p>
      ) : (
        <ul className="mt-4 space-y-4">
          {rows.map((r) => (
            <li key={r.name}>
              <div className="mb-1.5 flex items-baseline justify-between gap-3 text-sm">
                <span className="truncate font-medium text-ink">{r.name}</span>
                <span className="shrink-0 tabular-nums text-slate">
                  {r.winRate}% ·{" "}
                  <span
                    className={`font-semibold ${
                      r.netR >= 0 ? "text-long" : "text-short"
                    }`}
                  >
                    {r.netR >= 0 ? "+" : ""}
                    {r.netR}R
                  </span>
                </span>
              </div>
              <div className="h-1.5 overflow-hidden rounded-full bg-line">
                <div
                  className={`h-full rounded-full ${
                    r.winRate >= 50 ? "bg-long" : "bg-short"
                  }`}
                  style={{ width: `${Math.min(100, Math.max(0, r.winRate))}%` }}
                />
              </div>
              <p className="mt-1 text-xs text-slate">{r.count} ការជួញដូរ</p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
