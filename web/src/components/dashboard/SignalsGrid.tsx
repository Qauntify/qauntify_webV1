"use client";

import { useCallback, useEffect, useState } from "react";

import type { Signal } from "@/lib/signals";
import { formatDateTime, formatPrice, formatRelativeTime } from "@/lib/format";

function riskReward(signal: Signal): string {
  const risk = Math.abs(signal.entry - signal.stopLoss);
  if (risk === 0) return "—";
  const reward = Math.abs(signal.takeProfit - signal.entry);
  return `${(reward / risk).toFixed(1)}R`;
}

function DirectionPill({ direction }: { direction: Signal["direction"] }) {
  const isLong = direction === "long";
  return (
    <span
      className={`inline-flex items-center rounded-md px-2 py-0.5 font-mono text-[11px] font-semibold uppercase tracking-wide ${
        isLong ? "bg-long-soft text-long" : "bg-short-soft text-short"
      }`}
    >
      {isLong ? "Long" : "Short"}
    </span>
  );
}

function StatusPill({ status }: { status: Signal["status"] }) {
  if (status === "open") {
    return (
      <span className="inline-flex items-center rounded-md bg-line px-2 py-0.5 font-mono text-[11px] font-medium tracking-wide text-slate">
        Open
      </span>
    );
  }
  if (status === "expired") {
    return (
      <span className="inline-flex items-center rounded-md bg-line px-2 py-0.5 font-mono text-[11px] font-semibold uppercase tracking-wide text-slate">
        Expired
      </span>
    );
  }
  const isWin = status === "tp_hit";
  return (
    <span
      className={`inline-flex items-center rounded-md px-2 py-0.5 font-mono text-[11px] font-semibold uppercase tracking-wide ${
        isWin ? "bg-long-soft text-long" : "bg-short-soft text-short"
      }`}
    >
      {isWin ? "TP hit" : "SL hit"}
    </span>
  );
}

function ConfidenceBar({ value, compact = false }: { value: number; compact?: boolean }) {
  return (
    <div className={`flex items-center gap-2 ${compact ? "" : "w-full"}`}>
      <div className={`h-1.5 overflow-hidden rounded-full bg-line ${compact ? "w-16" : "flex-1"}`}>
        <div
          className="h-full rounded-full bg-accent"
          style={{ width: `${value}%` }}
        />
      </div>
      <span className="font-mono text-xs font-medium text-slate">{value}%</span>
    </div>
  );
}

export function SignalCard({
  signal,
  onSelect,
  adminSlot,
}: {
  signal: Signal;
  onSelect?: (signal: Signal) => void;
  adminSlot?: React.ReactNode;
}) {
  const isLong = signal.direction === "long";
  const Component = onSelect ? "button" : "div";

  return (
    <Component
      type={onSelect ? "button" : undefined}
      onClick={onSelect ? () => onSelect(signal) : undefined}
      className={`group relative w-full overflow-hidden rounded-xl border border-line bg-card text-left shadow-sm transition-all duration-300 hover:-translate-y-1 hover:border-accent/40 hover:shadow-xl hover:shadow-accent/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-paper`}
    >
      {/* Dynamic border based on direction */}
      <div className={`absolute left-0 top-0 bottom-0 w-1 ${isLong ? "bg-long" : "bg-short"} transition-all duration-300 group-hover:w-1.5`} />
      
      {/* Subtle background glow on hover */}
      <div className={`absolute inset-0 opacity-0 transition-opacity duration-300 group-hover:opacity-100 bg-gradient-to-br ${isLong ? "from-long/5" : "from-short/5"} to-transparent pointer-events-none`} />

      <div className="relative flex items-start justify-between gap-3 p-5 pb-4 pl-6">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-lg font-bold tracking-tight text-ink drop-shadow-sm">{signal.symbol}</span>
            <DirectionPill direction={signal.direction} />
          </div>
          <div className="mt-2 flex items-center gap-2">
            <span className="rounded-md bg-accent/10 px-2 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-wider text-accent border border-accent/20">
              {signal.timeframe}
            </span>
            <StatusPill status={signal.status} />
          </div>
        </div>
        <div className="flex flex-col items-end justify-center pt-1">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-slate/70 mb-1.5">Confidence</p>
          <ConfidenceBar value={signal.confidence} compact />
        </div>
      </div>

      <div className="relative grid grid-cols-3 gap-3 border-t border-line/50 px-6 py-4 bg-slate/5">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-wider text-slate/70 mb-1">Entry</p>
          <p className="font-mono text-sm font-bold text-ink">
            {formatPrice(signal.entry)}
          </p>
        </div>
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-wider text-slate/70 mb-1">Stop Loss</p>
          <p className="font-mono text-sm font-bold text-short drop-shadow-sm">
            {formatPrice(signal.stopLoss)}
          </p>
        </div>
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-wider text-slate/70 mb-1">Target</p>
          <p className="font-mono text-sm font-bold text-long drop-shadow-sm">
            {formatPrice(signal.takeProfit)}
          </p>
        </div>
      </div>

      <div className="relative flex items-center justify-between border-t border-line/50 px-6 py-3 bg-card transition-colors duration-300 group-hover:bg-slate/5">
        <span className="flex items-center gap-1.5 font-mono text-xs font-medium text-slate">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="opacity-70"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
          {formatRelativeTime(signal.createdAt)}
        </span>
        {adminSlot ? (
          <div className="z-10">{adminSlot}</div>
        ) : onSelect ? (
          <span className="flex items-center gap-1 text-xs font-semibold text-accent opacity-0 transition-all duration-300 transform translate-x-2 group-hover:translate-x-0 group-hover:opacity-100">
            View details 
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
          </span>
        ) : null}
      </div>
    </Component>
  );
}

function DetailRow({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "long" | "short" | "accent";
}) {
  const toneClass =
    tone === "long"
      ? "text-long"
      : tone === "short"
        ? "text-short"
        : tone === "accent"
          ? "text-accent"
          : "text-ink";

  return (
    <div className="rounded-lg border border-line bg-paper/50 px-4 py-3">
      <p className="text-[10px] font-medium uppercase tracking-wide text-slate">{label}</p>
      <p className={`mt-1 font-mono text-sm font-semibold ${toneClass}`}>{value}</p>
    </div>
  );
}

function SignalDetailModal({
  signal,
  onClose,
}: {
  signal: Signal;
  onClose: () => void;
}) {
  const handleKeyDown = useCallback(
    (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    },
    [onClose],
  );

  useEffect(() => {
    document.addEventListener("keydown", handleKeyDown);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = "";
    };
  }, [handleKeyDown]);

  const isLong = signal.direction === "long";

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center p-4 sm:items-center">
      <button
        type="button"
        aria-label="Close dialog"
        className="absolute inset-0 bg-ink/50 backdrop-blur-[2px]"
        onClick={onClose}
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="signal-detail-title"
        className={`relative z-10 flex max-h-[90vh] w-full max-w-2xl flex-col overflow-hidden rounded-xl border border-line bg-card shadow-[var(--shadow-card-hover)] ${
          isLong ? "border-t-[3px] border-t-long" : "border-t-[3px] border-t-short"
        }`}
      >
        <div className="flex items-start justify-between gap-4 border-b border-line px-5 py-4">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h2 id="signal-detail-title" className="font-mono text-xl font-bold text-ink">
                {signal.symbol}
              </h2>
              <DirectionPill direction={signal.direction} />
              <span className="rounded bg-accent-soft px-2 py-0.5 font-mono text-[10px] font-medium uppercase text-accent">
                {signal.timeframe}
              </span>
              <StatusPill status={signal.status} />
            </div>
            <p className="mt-1 text-sm text-slate">
              Opened {formatDateTime(signal.createdAt)}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="btn-ghost shrink-0 rounded-lg p-2"
            aria-label="Close"
          >
            <CloseIcon />
          </button>
        </div>

        <div className="overflow-y-auto px-5 py-5">
          <div className="mb-5">
            <p className="mb-2 text-xs font-medium uppercase tracking-wide text-slate">
              Confidence
            </p>
            <ConfidenceBar value={signal.confidence} />
          </div>

          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <DetailRow label="Entry" value={formatPrice(signal.entry)} />
            <DetailRow label="Stop loss" value={formatPrice(signal.stopLoss)} tone="short" />
            <DetailRow label="Take profit" value={formatPrice(signal.takeProfit)} tone="long" />
            <DetailRow label="Risk / reward" value={riskReward(signal)} tone="accent" />
          </div>

          <div className="mt-5 rounded-lg border border-line bg-accent-soft/30 p-4">
            <p className="text-xs font-medium uppercase tracking-wide text-slate">
              AI rationale
            </p>
            <p className="mt-2 text-sm leading-relaxed text-ink">{signal.rationale}</p>
          </div>

          <div className="mt-5">
            <p className="mb-3 text-xs font-medium uppercase tracking-wide text-slate">
              Indicators
            </p>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <DetailRow label="EMA 9" value={signal.indicators.ema9.toFixed(2)} />
              <DetailRow label="EMA 21" value={signal.indicators.ema21.toFixed(2)} />
              <DetailRow label="RSI" value={signal.indicators.rsi.toFixed(1)} />
              <DetailRow label="MACD hist" value={signal.indicators.macdHist.toFixed(4)} />
            </div>
          </div>

          {signal.newsHeadlines.length > 0 ? (
            <div className="mt-5">
              <p className="mb-3 text-xs font-medium uppercase tracking-wide text-slate">
                News reviewed ({signal.newsHeadlines.length})
              </p>
              <ul className="space-y-2">
                {signal.newsHeadlines.map((headline) => (
                  <li
                    key={headline}
                    className="rounded-lg border border-line bg-paper/50 px-4 py-2.5 text-sm text-slate"
                  >
                    {headline}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function CloseIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <path d="M18 6 6 18M6 6l12 12" />
    </svg>
  );
}

export function SignalsGrid({ signals }: { signals: Signal[] }) {
  const [selected, setSelected] = useState<Signal | null>(null);

  return (
    <>
      <div className="grid w-full gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
        {signals.map((signal) => (
          <SignalCard key={signal.id} signal={signal} onSelect={setSelected} />
        ))}
      </div>
      {selected ? (
        <SignalDetailModal signal={selected} onClose={() => setSelected(null)} />
      ) : null}
    </>
  );
}
