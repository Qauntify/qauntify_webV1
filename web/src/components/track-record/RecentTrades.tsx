import type { ClosedTrade } from "@/lib/track-record";
import { tradeR } from "@/lib/track-record";
import { relativeTime } from "@/lib/relative-time";

export function RecentTrades({ trades }: { trades: ClosedTrade[] }) {
  if (trades.length === 0) return <div className="text-sm text-slate/60">No closed trades yet.</div>;
  return (
    <div className="divide-y divide-line/60">
      {trades.map((t) => {
        const win = tradeR(t) > 0;
        const label = win
          ? t.reached >= 3
            ? "✓ TP3"
            : t.reached >= 2
              ? "✓ TP2"
              : "✓ TP1"
          : "✗ SL";
        return (
          <div key={t.id} className="grid grid-cols-[auto_1fr_auto_auto] items-center gap-3 py-2 text-sm">
            {t.outcomeChartUrl ? (
              <a href={t.outcomeChartUrl} target="_blank" rel="noopener noreferrer">
                <img src={t.outcomeChartUrl} alt={`${t.symbol} outcome`} loading="lazy" className="h-8 w-14 rounded border border-line object-cover" />
              </a>
            ) : (
              <div className="h-8 w-14 rounded border border-line bg-slate/10" />
            )}
            <div>
              <span className="font-semibold text-ink">{t.symbol}</span>{" "}
              <span className="text-slate/60">{t.timeframe}</span>{" "}
              <span className={t.direction === "long" ? "text-emerald-400" : "text-rose-400"}>{t.direction.toUpperCase()}</span>
            </div>
            <div className={`text-xs font-bold ${win ? "text-emerald-400" : "text-rose-400"}`}>{label}</div>
            <div className="text-right text-slate/60">{relativeTime(t.closedAt)}</div>
          </div>
        );
      })}
    </div>
  );
}
