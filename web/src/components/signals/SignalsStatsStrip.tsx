import type { Stats } from "@/lib/signals";

/** Dense mono strip for the signals desk — different from StatsBar tiles. */
export function SignalsStatsStrip({ stats }: { stats: Stats }) {
  const cells = [
    { k: "TOTAL", v: String(stats.total) },
    {
      k: "AVG CONF",
      v: stats.total > 0 ? `${Math.round(stats.avgConfidence)}%` : "—",
    },
    { k: "LONG", v: String(stats.longs), tone: "long" as const },
    { k: "SHORT", v: String(stats.shorts), tone: "short" as const },
    {
      k: "WIN RATE",
      v: stats.winRate !== null ? `${stats.winRate}%` : "—",
      sub:
        stats.winRate !== null
          ? `${stats.tpHits}F · ${stats.partialWins}P · ${stats.slHits}L`
          : undefined,
    },
  ];

  return (
    <div className="overflow-hidden rounded-lg border border-line bg-card">
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5">
        {cells.map((cell, i) => (
          <div
            key={cell.k}
            className={`px-4 py-3 ${
              i > 0 ? "border-t border-line sm:border-t-0 sm:border-l" : ""
            } ${i === 2 ? "sm:border-l" : ""} ${
              i >= 3 ? "lg:border-l" : ""
            }`}
          >
            <p className="font-mono text-[10px] font-semibold tracking-[0.16em] text-slate">
              {cell.k}
            </p>
            <p
              className={`mt-1 font-mono text-xl font-bold tabular-nums tracking-tight ${
                cell.tone === "long"
                  ? "text-long"
                  : cell.tone === "short"
                    ? "text-short"
                    : "text-ink"
              }`}
            >
              {cell.v}
            </p>
            {cell.sub ? (
              <p className="mt-0.5 font-mono text-[10px] text-slate">{cell.sub}</p>
            ) : null}
          </div>
        ))}
      </div>
    </div>
  );
}
