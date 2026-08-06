import type { ClosedTrade } from "@/lib/track-record";
import { tradeR } from "@/lib/track-record";
import { formatPrice } from "@/lib/format";
import { relativeTime } from "@/lib/relative-time";

function outcomeLabel(reached: number): string {
  if (reached >= 3) return "TP3";
  if (reached >= 2) return "TP2";
  if (reached >= 1) return "TP1";
  return "SL";
}

function ClosedTradeCard({ trade }: { trade: ClosedTrade }) {
  const isLong = trade.direction === "long";
  const r = tradeR(trade);
  const win = trade.reached >= 1;
  const isSl = trade.status === "sl_hit" && trade.reached === 0;
  const label = outcomeLabel(trade.reached);
  const rText = `${r > 0 ? "+" : ""}${r.toFixed(2)}R`;

  const body = (
    <>
      {trade.outcomeChartUrl ? (
        <div className="relative aspect-[16/9] overflow-hidden border-b border-line bg-slate/5">
          <img
            src={trade.outcomeChartUrl}
            alt={`${trade.symbol} outcome chart`}
            loading="lazy"
            className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-[1.02]"
          />
        </div>
      ) : (
        <div className="flex aspect-[16/9] items-center justify-center border-b border-line bg-slate/5">
          <span className="font-mono text-[10px] uppercase tracking-wider text-slate/50">
            No outcome chart
          </span>
        </div>
      )}

      <div className="relative flex items-start justify-between gap-3 p-5 pb-4 pl-6">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-lg font-bold tracking-tight text-ink">
              {trade.symbol}
            </span>
            <span
              className={`rounded-md px-2 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-wider ${
                isLong
                  ? "bg-long/10 text-long border border-long/20"
                  : "bg-short/10 text-short border border-short/20"
              }`}
            >
              {trade.direction}
            </span>
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <span className="rounded-md border border-accent/20 bg-accent/10 px-2 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-wider text-accent">
              {trade.timeframe}
            </span>
            <span className="rounded-md border border-line bg-slate/5 px-2 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-wider text-slate">
              {trade.strategy.replace(/_/g, " ")}
            </span>
          </div>
        </div>
        <div className="flex flex-col items-end pt-0.5">
          <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-slate/70">
            Result
          </p>
          <span
            className={`font-mono text-sm font-bold ${
              win ? "text-long" : "text-short"
            }`}
          >
            {win ? `✓ ${label}` : `✗ ${label}`}
          </span>
          <span
            className={`mt-0.5 font-mono text-xs font-semibold ${
              r > 0 ? "text-long" : r < 0 ? "text-short" : "text-slate"
            }`}
          >
            {rText}
          </span>
        </div>
      </div>

      <div className="relative grid grid-cols-3 gap-3 border-t border-line/50 bg-slate/5 px-6 py-4">
        <div>
          <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-slate/70">
            Entry
          </p>
          <p className="font-mono text-sm font-bold text-ink">
            {formatPrice(trade.entry)}
          </p>
        </div>
        <div>
          <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-slate/70">
            Stop
          </p>
          <p className="font-mono text-sm font-bold text-short">
            {formatPrice(trade.stopLoss)}
          </p>
        </div>
        <div>
          <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-slate/70">
            Targets
          </p>
          <p className="font-mono text-sm font-bold text-long">
            {trade.targets.map((p) => formatPrice(p)).join(" / ") || "—"}
          </p>
        </div>
      </div>

      <div className="relative flex items-center justify-between border-t border-line/50 px-6 py-3">
        <span className="font-mono text-xs font-medium text-slate">
          Closed {relativeTime(trade.closedAt)}
        </span>
        {trade.outcomeChartUrl ? (
          <span className="text-xs font-semibold text-accent opacity-0 transition-opacity duration-300 group-hover:opacity-100">
            View chart →
          </span>
        ) : null}
      </div>
    </>
  );

  const className = `group relative w-full overflow-hidden rounded-lg border border-line bg-card text-left transition-colors hover:border-ink/25 ${
    isSl ? "opacity-70 grayscale hover:opacity-90" : ""
  }`;

  if (trade.outcomeChartUrl) {
    return (
      <a
        href={trade.outcomeChartUrl}
        target="_blank"
        rel="noopener noreferrer"
        className={`${className} block focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ink focus-visible:ring-offset-2 focus-visible:ring-offset-paper`}
      >
        <div
          className={`absolute bottom-0 left-0 top-0 w-1 ${
            isLong ? "bg-long" : "bg-short"
          }`}
        />
        {body}
      </a>
    );
  }

  return (
    <div className={className}>
      <div
        className={`absolute bottom-0 left-0 top-0 w-1 ${
          isLong ? "bg-long" : "bg-short"
        }`}
      />
      {body}
    </div>
  );
}

export function RecentTrades({ trades }: { trades: ClosedTrade[] }) {
  if (trades.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-line bg-card p-10 text-center text-sm text-slate/70">
        No closed trades yet.
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-3">
      {trades.map((trade) => (
        <ClosedTradeCard key={trade.id} trade={trade} />
      ))}
    </div>
  );
}
