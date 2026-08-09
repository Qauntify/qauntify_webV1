import type { Signal } from "@/lib/signals";
import { formatPrice, formatRelativeTime, formatTimeframe } from "@/lib/format";

function DirectionBadge({ direction }: { direction: Signal["direction"] }) {
  const isLong = direction === "long";
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 font-mono text-[11px] font-semibold uppercase tracking-wide ${
        isLong ? "bg-long-soft text-long" : "bg-short-soft text-short"
      }`}
    >
      {isLong ? "ទិញ" : "លក់"}
    </span>
  );
}

function StatusBadge({
  status,
  closedAt,
}: {
  status: Signal["status"];
  closedAt?: string | null;
}) {
  if (status === "open") return null;
  if (status === "expired") {
    return (
      <span className="inline-flex items-center rounded-md bg-line px-2 py-0.5 font-mono text-[11px] font-semibold uppercase tracking-wide text-slate">
        ផុតកំណត់
      </span>
    );
  }
  // Open partials (no closedAt) stay accent; closed TP1/TP2 wins go green.
  if ((status === "tp1_hit" || status === "tp2_hit") && !closedAt) {
    return (
      <span className="inline-flex items-center rounded-md bg-accent-soft px-2 py-0.5 font-mono text-[11px] font-semibold uppercase tracking-wide text-accent">
        {status === "tp1_hit" ? "ឈានដល់ TP1" : "ឈានដល់ TP2"}
      </span>
    );
  }
  const label =
    status === "tp3_hit"
      ? "ឈានដល់ TP3"
      : status === "tp2_hit"
        ? "ឈានដល់ TP2"
        : status === "tp1_hit"
          ? "ឈានដល់ TP1"
          : status === "tp_hit"
            ? "ឈានដល់ TP"
            : "ឈានដល់ SL";
  const isWin = status !== "sl_hit";
  return (
    <span
      className={`inline-flex items-center rounded-md px-2 py-0.5 font-mono text-[11px] font-semibold uppercase tracking-wide ${
        isWin ? "bg-long-soft text-long" : "bg-short-soft text-short"
      }`}
    >
      {label}
    </span>
  );
}

function ConfidenceGauge({ value }: { value: number }) {
  return (
    <div className="flex items-center gap-2" title={`ទំនុកចិត្ត ${value}/100`}>
      <div className="h-1.5 w-20 overflow-hidden rounded-full bg-line">
        <div
          className="h-full rounded-full bg-ink transition-all duration-300 ease-out"
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
      <div className="flex items-center justify-between border-b border-line px-4 py-2.5">
        <div className="flex flex-wrap items-center gap-2">
          <DirectionBadge direction={signal.direction} />
          <span className="font-mono text-sm font-bold">{signal.symbol}</span>
          <span className="rounded bg-line px-1.5 py-0.5 font-mono text-[10px] font-medium uppercase text-slate">
            {formatTimeframe(signal.timeframe)}
          </span>
          <StatusBadge status={signal.status} closedAt={signal.closedAt} />
        </div>
        <ConfidenceGauge value={signal.confidence} />
      </div>

      <div className="grid grid-cols-2 gap-3 px-4 py-3.5 sm:grid-cols-3 lg:grid-cols-5">
        <PriceCell label="ចូល" value={signal.entry} />
        <PriceCell label="បញ្ឈប់ខាត" value={signal.stopLoss} tone="short" />
        <PriceCell
          label={signal.takeProfit2 != null || signal.takeProfit3 != null ? "TP1" : "យកប្រាក់ចំណេញ"}
          value={signal.takeProfit}
          tone="long"
        />
        {signal.takeProfit2 != null ? (
          <PriceCell label="TP2" value={signal.takeProfit2} tone="long" />
        ) : null}
        {signal.takeProfit3 != null ? (
          <PriceCell label="TP3" value={signal.takeProfit3} tone="long" />
        ) : null}
      </div>

      {showRationale && signal.rationale && (
        <p className="border-t border-line bg-[#f8fafc] px-4 py-3 text-sm leading-relaxed text-slate dark:bg-white/5">
          {signal.rationale}
        </p>
      )}

      <div className="flex items-center justify-between border-t border-line px-4 py-2 text-xs text-slate">
        <span className="font-mono">
          {sample ? "example signal" : formatRelativeTime(signal.createdAt)}
        </span>
        <div className="flex items-center gap-3">
          {signal.newsHeadlines.length > 0 && (
            <span>
              បានពិនិត្យចំណងជើង {signal.newsHeadlines.length}
            </span>
          )}
          {adminSlot}
        </div>
      </div>
    </article>
  );
}
