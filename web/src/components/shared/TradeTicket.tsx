import type { Signal } from "@/lib/signals";
import { formatPrice, formatRelativeTime } from "@/lib/format";

function DirectionBadge({ direction }: { direction: Signal["direction"] }) {
  const isLong = direction === "long";
  return (
    <span
      className={`inline-flex items-center gap-1 rounded px-2 py-0.5 font-mono text-xs font-semibold uppercase tracking-wide ${
        isLong ? "bg-long-soft text-long" : "bg-short-soft text-short"
      }`}
    >
      {isLong ? "▲ Long" : "▼ Short"}
    </span>
  );
}

function StatusBadge({ status }: { status: Signal["status"] }) {
  if (status === "open") return null;
  const isWin = status === "tp_hit";
  return (
    <span
      className={`inline-flex items-center rounded px-2 py-0.5 font-mono text-xs font-semibold uppercase tracking-wide ${
        isWin ? "bg-long-soft text-long" : "bg-short-soft text-short"
      }`}
    >
      {isWin ? "TP hit" : "SL hit"}
    </span>
  );
}

function ConfidenceGauge({ value }: { value: number }) {
  return (
    <div className="flex items-center gap-2" title={`Confidence ${value}/100`}>
      <div className="h-1 w-16 overflow-hidden rounded-full bg-line">
        <div className="h-full rounded-full bg-ink" style={{ width: `${value}%` }} />
      </div>
      <span className="font-mono text-xs text-slate">{value}</span>
    </div>
  );
}

function PriceCell({ label, value, tone }: { label: string; value: number; tone?: "long" | "short" }) {
  const toneClass = tone === "long" ? "text-long" : tone === "short" ? "text-short" : "text-ink";
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[11px] uppercase tracking-wider text-slate">{label}</span>
      <span className={`font-mono text-sm font-medium ${toneClass}`}>{formatPrice(value)}</span>
    </div>
  );
}

export function TradeTicket({
  signal,
  sample = false,
  showRationale = true,
}: {
  signal: Signal;
  sample?: boolean;
  showRationale?: boolean;
}) {
  return (
    <article className="rounded-xl border border-line bg-card shadow-[0_1px_3px_rgba(16,24,40,0.06)] transition-shadow hover:shadow-[0_4px_12px_rgba(16,24,40,0.08)]">
      <div className="flex items-center justify-between border-b border-line px-5 py-3">
        <div className="flex items-center gap-3">
          <DirectionBadge direction={signal.direction} />
          <span className="font-mono text-sm font-semibold">{signal.symbol}</span>
          <span className="font-mono text-xs text-slate">{signal.timeframe}</span>
          <StatusBadge status={signal.status} />
        </div>
        <ConfidenceGauge value={signal.confidence} />
      </div>

      <div className="grid grid-cols-3 gap-4 px-5 py-4">
        <PriceCell label="Entry" value={signal.entry} />
        <PriceCell label="Stop loss" value={signal.stopLoss} tone="short" />
        <PriceCell label="Take profit" value={signal.takeProfit} tone="long" />
      </div>

      {showRationale && signal.rationale && (
        <p className="border-t border-line px-5 py-3 font-display text-[15px] italic leading-snug text-slate">
          “{signal.rationale}”
        </p>
      )}

      <div className="flex items-center justify-between border-t border-line px-5 py-2.5 text-xs text-slate">
        <span className="font-mono">
          {sample ? "example signal" : formatRelativeTime(signal.createdAt)}
        </span>
        {signal.newsHeadlines.length > 0 && (
          <span>
            {signal.newsHeadlines.length} headline
            {signal.newsHeadlines.length === 1 ? "" : "s"} reviewed
          </span>
        )}
      </div>
    </article>
  );
}
