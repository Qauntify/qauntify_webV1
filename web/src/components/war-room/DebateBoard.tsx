import type { Debate } from "@/lib/debates";

const VERDICT: Record<string, { label: string; cls: string }> = {
  agree: { label: "AGREE", cls: "bg-long-soft text-long" },
  reject: { label: "REJECT", cls: "bg-short-soft text-short" },
  caution: { label: "CAUTION", cls: "bg-accent-soft text-accent" },
};

function DebateCard({ debate }: { debate: Debate }) {
  const isLong = debate.direction === "long";
  const verdict = VERDICT[debate.managerVerdict] ?? VERDICT.caution;
  return (
    <article className="stat-tile">
      <header className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="font-mono font-semibold text-ink">{debate.symbol}</span>
          <span className="rounded-md bg-accent-soft px-2 py-0.5 font-mono text-xs text-accent">
            {debate.timeframe}
          </span>
        </div>
        <span
          className={`rounded-md px-2 py-0.5 font-mono text-[11px] font-semibold uppercase tracking-wide ${
            isLong ? "bg-long-soft text-long" : "bg-short-soft text-short"
          }`}
        >
          {isLong ? "Long" : "Short"}
        </span>
      </header>

      <div className="mt-4 space-y-3">
        {debate.transcript.map((m, i) => (
          <div
            key={i}
            className="flex gap-3 animate-fade-up"
            style={{ animationDelay: `${i * 250}ms` }}
          >
            <span
              aria-hidden
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-line bg-card text-lg"
            >
              {m.avatar}
            </span>
            <div className="min-w-0">
              <p className="text-xs font-semibold text-slate">{m.agent}</p>
              <p className="text-sm leading-relaxed text-ink">{m.message}</p>
            </div>
          </div>
        ))}
      </div>

      <footer className="mt-4 flex items-center justify-between border-t border-line pt-3">
        <span className="text-xs text-slate">Manager verdict</span>
        <div className="flex items-center gap-2">
          <span className="font-mono text-xs text-slate">
            {debate.managerConfidence}%
          </span>
          <span
            className={`rounded-md px-2 py-0.5 font-mono text-[11px] font-semibold ${verdict.cls}`}
          >
            {verdict.label}
          </span>
        </div>
      </footer>
    </article>
  );
}

export function DebateBoard({ debates }: { debates: Debate[] }) {
  if (debates.length === 0) {
    return (
      <div className="stat-tile py-12 text-center">
        <p className="text-3xl">🤖💬🧑‍💼</p>
        <p className="mt-3 font-semibold text-ink">The war room is warming up.</p>
        <p className="mt-1 text-sm text-slate">
          Debates appear here as the AI confirms new signals.
        </p>
      </div>
    );
  }
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      {debates.map((d) => (
        <DebateCard key={d.id} debate={d} />
      ))}
    </div>
  );
}
