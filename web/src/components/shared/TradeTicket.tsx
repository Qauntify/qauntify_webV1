import type { Signal } from "@/lib/signals";
import { formatPrice, formatRelativeTime } from "@/lib/format";

function DirectionBadge({ direction }: { direction: Signal["direction"] }) {
  const isLong = direction === "long";
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 font-mono text-[11px] font-semibold uppercase tracking-wide ${
        isLong ? "bg-long-soft text-long" : "bg-short-soft text-short"
      }`}
    >
      {isLong ? "Long" : "Short"}
    </span>
  );
}

function StatusBadge({ status }: { status: Signal["status"] }) {
  if (status === "open") return null;
  if (status === "expired") {
    return (
      <span className="inline-flex items-center rounded-md bg-line px-2 py-0.5 font-mono text-[11px] font-semibold uppercase tracking-wide text-slate">
        Expired
      </span>
    );
  }
  if (status === "tp1_hit" || status === "tp2_hit") {
    return (
      <span className="inline-flex items-center rounded-md bg-accent-soft px-2 py-0.5 font-mono text-[11px] font-semibold uppercase tracking-wide text-accent">
        {status === "tp1_hit" ? "TP1 hit" : "TP2 hit"}
      </span>
    );
  }
  const isWin = status === "tp_hit" || status === "tp3_hit";
  return (
    <span
      className={`inline-flex items-center rounded-md px-2 py-0.5 font-mono text-[11px] font-semibold uppercase tracking-wide ${
        isWin ? "bg-long-soft text-long" : "bg-short-soft text-short"
      }`}
    >
      {isWin ? (status === "tp3_hit" ? "TP3 hit" : "TP hit") : "SL hit"}
    </span>
  );
}

function ConfidenceGauge({ value }: { value: number }) {
  return (
    <div className="flex items-center gap-2" title={`Confidence ${value}/100`}>
      <div className="h-1.5 w-20 overflow-hidden rounded-full bg-line">
        <div
          className="h-full rounded-full bg-accent transition-all"
          style={{ width: `${value}%` }}
        />
      </div>
      <span className="font-mono text-xs font-medium text-slate">{value}%</span>
    </div>
  );
}

function PriceCell({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone?: "long" | "short";
}) {
  const toneClass =
    tone === "long" ? "text-long" : tone === "short" ? "text-short" : "text-ink";
  return (
    <div className="flex flex-col gap-1">
      <span className="stat-tile-label">{label}</span>
      <span className={`font-mono text-sm font-semibold ${toneClass}`}>
        {formatPrice(value)}
      </span>
    </div>
  );
}

export function TradeTicket({
  signal,
  sample = false,
  showRationale = true,
  adminSlot,
}: {
  signal: Signal;
  sample?: boolean;
  showRationale?: boolean;
  adminSlot?: React.ReactNode;
}) {
  const isLong = signal.direction === "long";
  return (
    <article
      className={`card-surface overflow-hidden border-l-[3px] ${
        isLong ? "border-l-long" : "border-l-short"
      }`}
    >
      <div className="flex items-center justify-between border-b border-line px-5 py-3.5">
        <div className="flex flex-wrap items-center gap-2.5">
          <DirectionBadge direction={signal.direction} />
          <span className="font-mono text-sm font-bold">{signal.symbol}</span>
          <span className="rounded bg-accent-soft px-1.5 py-0.5 font-mono text-[10px] font-medium uppercase text-accent">
            {signal.timeframe}
          </span>
          <StatusBadge status={signal.status} />
        </div>
        <ConfidenceGauge value={signal.confidence} />
      </div>

      <div className="grid grid-cols-2 gap-4 px-5 py-5 sm:grid-cols-4">
        <PriceCell label="Entry" value={signal.entry} />
        <PriceCell label="Stop loss" value={signal.stopLoss} tone="short" />
        <PriceCell
          label={signal.takeProfit2 != null || signal.takeProfit3 != null ? "TP1" : "Take profit"}
          value={signal.takeProfit}
          tone="long"
        />
        {signal.takeProfit3 != null ? (
          <PriceCell label="TP3" value={signal.takeProfit3} tone="long" />
        ) : signal.takeProfit2 != null ? (
          <PriceCell label="TP2" value={signal.takeProfit2} tone="long" />
        ) : null}
      </div>

      {showRationale && signal.rationale && (
        <p className="border-t border-line bg-accent-soft/30 px-5 py-3.5 text-sm leading-relaxed text-slate">
          {signal.rationale}
        </p>
      )}

      <div className="flex items-center justify-between border-t border-line px-5 py-2.5 text-xs text-slate">
        <span className="font-mono">
          {sample ? "example signal" : formatRelativeTime(signal.createdAt)}
        </span>
        <div className="flex items-center gap-3">
          {signal.newsHeadlines.length > 0 && (
            <span>
              {signal.newsHeadlines.length} headline
              {signal.newsHeadlines.length === 1 ? "" : "s"} reviewed
            </span>
          )}
          {adminSlot}
        </div>
      </div>
    </article>
  );
}
