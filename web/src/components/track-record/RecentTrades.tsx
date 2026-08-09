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
  const strategy = trade.strategy.replace(/_/g, " ");

  const body = (
    <>
      {trade.outcomeChartUrl ? (
        <div className="relative aspect-[16/9] overflow-hidden border-b border-line bg-paper">
          <img
            src={trade.outcomeChartUrl}
            alt={`${trade.symbol} outcome chart`}
            loading="lazy"
            className="h-full w-full object-cover"
          />
        </div>
      ) : (
        <div className="flex aspect-[16/9] items-center justify-center border-b border-line bg-paper">
          <span className="text-xs text-slate">គ្មានគំនូសតាង</span>
        </div>
      )}

      <div className="relative flex items-start justify-between gap-3 p-5 pl-6">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-lg font-bold tracking-tight text-ink">
              {trade.symbol}
            </span>
            <span
              className={`rounded-md px-2 py-0.5 text-[11px] font-semibold uppercase ${
                isLong ? "bg-long-soft text-long" : "bg-short-soft text-short"
              }`}
            >
              {isLong ? "ទិញ" : "លក់"}
            </span>
          </div>
          <p className="mt-1.5 truncate text-sm text-slate">
            {trade.timeframe} · {strategy}
          </p>
        </div>
        <div className="shrink-0 text-right">
          <p
            className={`font-mono text-sm font-bold ${
              win ? "text-long" : "text-short"
            }`}
          >
            {win ? label : label}
          </p>
          <p
            className={`mt-0.5 font-mono text-xs font-semibold ${
              r > 0 ? "text-long" : r < 0 ? "text-short" : "text-slate"
            }`}
          >
            {rText}
          </p>
        </div>
      </div>

      <div className="relative grid grid-cols-3 gap-3 border-t border-line px-5 py-4 pl-6">
        <div>
          <p className="text-xs text-slate">ចូល</p>
          <p className="mt-0.5 font-mono text-sm font-semibold text-ink">
            {formatPrice(trade.entry)}
          </p>
        </div>
        <div>
          <p className="text-xs text-slate">បញ្ឈប់</p>
          <p className="mt-0.5 font-mono text-sm font-semibold text-short">
            {formatPrice(trade.stopLoss)}
          </p>
        </div>
        <div>
          <p className="text-xs text-slate">គោលដៅ</p>
          <p className="mt-0.5 font-mono text-sm font-semibold text-long">
            {trade.targets.map((p) => formatPrice(p)).join(" / ") || "—"}
          </p>
        </div>
      </div>

      <div className="relative border-t border-line px-5 py-3 pl-6">
        <span className="text-xs text-slate">
          បិទ {relativeTime(trade.closedAt)}
        </span>
      </div>
    </>
  );

  const className = `group relative w-full overflow-hidden rounded-xl border border-line bg-card text-left transition-colors hover:border-ink/20 ${
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
      <div className="rounded-xl border border-dashed border-line bg-card px-6 py-14 text-center">
        <p className="text-sm font-semibold text-ink">មិនទាន់មានការជួញដូរបិទទេ</p>
        <p className="mx-auto mt-1.5 max-w-sm text-sm text-slate">
          លទ្ធផលនឹងបង្ហាញនៅទីនេះនៅពេលការជួញដូរបិទ។
        </p>
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
