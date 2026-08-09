import type { Stats } from "@/lib/signals";

const STEPS = [
  { id: "scan", label: "ស្កេន" },
  { id: "setup", label: "ការរៀបចំ" },
  { id: "news", label: "ព័ត៌មាន" },
  { id: "ai", label: "AI បញ្ជាក់" },
  { id: "publish", label: "បានផ្សាយ" },
] as const;

function StatBar({
  label,
  value,
  tone = "ink",
}: {
  label: string;
  value: number;
  tone?: "ink" | "long";
}) {
  return (
    <div>
      <div className="flex items-center justify-between text-xs">
        <span className="font-medium text-slate">{label}</span>
        <span
          className={`font-mono font-bold ${
            tone === "long" ? "text-long" : "text-ink"
          }`}
        >
          {value}%
        </span>
      </div>
      <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-line">
        <div
          className={`h-full rounded-full transition-all duration-500 ${
            tone === "long" ? "bg-long" : "bg-ink"
          }`}
          style={{ width: `${Math.min(100, Math.max(0, value))}%` }}
        />
      </div>
    </div>
  );
}

export function HowAiWorks({ stats }: { stats: Stats }) {
  return (
    <div
      id="how-ai-works"
      className="overflow-hidden rounded-lg border border-line bg-paper"
    >
      <div className="flex items-center justify-between px-4 py-3">
        <p className="font-mono text-[11px] font-semibold uppercase tracking-[0.14em] text-ink">
          វដ្តម៉ាស៊ីន
        </p>
        <span className="inline-flex items-center gap-1.5 font-mono text-[10px] font-semibold uppercase tracking-wide text-long">
          <span className="h-1.5 w-1.5 rounded-full bg-long" aria-hidden />
          ផ្ទាល់
        </span>
      </div>

      <ol className="grid grid-cols-5 gap-px border-y border-line bg-line">
        {STEPS.map((s) => (
          <li
            key={s.id}
            className="flex flex-col items-center gap-1.5 bg-card px-1 py-3 text-center"
          >
            <span
              className="flex h-5 w-5 items-center justify-center rounded-full bg-long-soft text-[10px] font-bold text-long"
              aria-hidden
            >
              ✓
            </span>
            <span className="text-[10px] font-semibold leading-tight text-ink">
              {s.label}
            </span>
          </li>
        ))}
      </ol>

      <div className="p-4">
        <p className="mb-3 font-mono text-[10px] font-semibold uppercase tracking-wide text-slate">
          កំណត់ត្រាលទ្ធផលរហូតមកដល់ពេលនេះ
        </p>
        <div className="mb-4 flex items-baseline gap-1.5">
          <span className="font-mono text-2xl font-bold text-ink">
            {stats.total}
          </span>
          <span className="text-xs text-slate">signals logged</span>
        </div>
        <div className="flex flex-col gap-3">
          <StatBar label="ទំនុកចិត្តមធ្យម" value={stats.avgConfidence} />
          {stats.winRate !== null ? (
            <StatBar label="អត្រាឈ្នះ" value={stats.winRate} tone="long" />
          ) : null}
        </div>
      </div>
    </div>
  );
}
