"use client";

import { useCallback, useEffect, useState } from "react";

import type { Signal } from "@/lib/signals";
import { formatDateTime, formatPrice, formatRelativeTime, formatTimeframe } from "@/lib/format";
import { SignalWarRoomSection } from "@/components/dashboard/SignalWarRoomSection";

function riskReward(signal: Signal): string {
  const risk = Math.abs(signal.entry - signal.stopLoss);
  if (risk === 0) return "—";
  const target = signal.takeProfit3 ?? signal.takeProfit;
  const reward = Math.abs(target - signal.entry);
  return `${(reward / risk).toFixed(1)}R`;
}

function fmtNum(value: number | undefined, digits: number): string | null {
  if (value === undefined) return null;
  return value.toFixed(digits);
}

function indicatorRows(signal: Signal): { label: string; value: string }[] {
  const ind = signal.indicators;
  const rows: { label: string; value: string }[] = [];
  if (ind.strategy === "ce_lwma" || ind.ceTrail !== undefined || ind.lwma200 !== undefined) {
    const trail = fmtNum(ind.ceTrail, 4);
    if (trail) rows.push({ label: "CE trail", value: trail });
    if (ind.ceDirection) rows.push({ label: "CE dir", value: ind.ceDirection });
    const lwma = fmtNum(ind.lwma200, 4);
    if (lwma) rows.push({ label: "LWMA 200", value: lwma });
    if (ind.zone) rows.push({ label: "តំបន់", value: ind.zone });
    return rows.length > 0 ? rows : [{ label: "យុទ្ធសាស្ត្រ", value: "CE + LWMA" }];
  }
  if (ind.strategy === "ict_smc" || ind.structure) {
    if (ind.structure) rows.push({ label: "រចនាសម្ព័ន្ធ", value: ind.structure });
    const sweep = fmtNum(ind.sweepLevel, 2);
    if (sweep) rows.push({ label: "Sweep", value: sweep });
    const choch = fmtNum(ind.chochLevel, 2);
    if (choch) rows.push({ label: "CHoCH", value: choch });
    const atr = fmtNum(ind.atr, 4);
    if (atr) rows.push({ label: "ATR", value: atr });
    const adx = fmtNum(ind.adx, 1);
    if (adx) rows.push({ label: "ADX", value: adx });
    if (ind.htfTrend) rows.push({ label: "និន្នាការ HTF", value: ind.htfTrend });
    return rows.length > 0 ? rows : [{ label: "យុទ្ធសាស្ត្រ", value: "ICT / SMC" }];
  }
  if (ind.strategy === "sr_zone" || ind.zoneLow !== undefined) {
    if (ind.side) rows.push({ label: "ភាគី", value: ind.side });
    const lo = fmtNum(ind.zoneLow, 2);
    const hi = fmtNum(ind.zoneHigh, 2);
    if (lo && hi) rows.push({ label: "តំបន់", value: `${lo}–${hi}` });
    if (ind.touches !== undefined) {
      rows.push({ label: "ការប៉ះ", value: String(ind.touches) });
    }
    const atr = fmtNum(ind.atr, 4);
    if (atr) rows.push({ label: "ATR", value: atr });
    const adx = fmtNum(ind.adx, 1);
    if (adx) rows.push({ label: "ADX", value: adx });
    if (ind.htfTrend) rows.push({ label: "និន្នាការ HTF", value: ind.htfTrend });
    return rows.length > 0 ? rows : [{ label: "យុទ្ធសាស្ត្រ", value: "S/R bounce" }];
  }
  if (ind.strategy === "cloud_mss" || ind.cloudLow !== undefined) {
    if (ind.side) rows.push({ label: "ភាគី", value: ind.side });
    if (ind.ceTrend) rows.push({ label: "CE trend", value: ind.ceTrend });
    const lo = fmtNum(ind.cloudLow, 2);
    const hi = fmtNum(ind.cloudHigh, 2);
    if (lo && hi) rows.push({ label: "Cloud", value: `${lo}–${hi}` });
    const ma200 = fmtNum(ind.ma200, 2);
    if (ma200) rows.push({ label: "MA200", value: ma200 });
    const choch = fmtNum(ind.chochLevel, 2);
    if (choch) rows.push({ label: "CHoCH", value: choch });
    const atr = fmtNum(ind.atr, 4);
    if (atr) rows.push({ label: "ATR", value: atr });
    const adx = fmtNum(ind.adx, 1);
    if (adx) rows.push({ label: "ADX", value: adx });
    if (ind.htfTrend) rows.push({ label: "និន្នាការ HTF", value: ind.htfTrend });
    return rows.length > 0 ? rows : [{ label: "យុទ្ធសាស្ត្រ", value: "Cloud + MSS" }];
  }
  if (ind.strategy === "bbma_extreme" || ind.strategy === "bbma_reentry" || ind.bbUpper !== undefined) {
    if (ind.side) rows.push({ label: "ភាគី", value: ind.side });
    if (ind.trigger) rows.push({ label: "កេះ", value: ind.trigger });
    const upper = fmtNum(ind.bbUpper, 2);
    const lower = fmtNum(ind.bbLower, 2);
    if (upper && lower) rows.push({ label: "BB band", value: `${lower}–${upper}` });
    const ma5h = fmtNum(ind.ma5h, 2);
    const ma5l = fmtNum(ind.ma5l, 2);
    if (ma5h && ma5l) rows.push({ label: "MA5 band", value: `${ma5l}–${ma5h}` });
    const atr = fmtNum(ind.atr, 4);
    if (atr) rows.push({ label: "ATR", value: atr });
    const adx = fmtNum(ind.adx, 1);
    if (adx) rows.push({ label: "ADX", value: adx });
    if (ind.htfTrend) rows.push({ label: "និន្នាការ HTF", value: ind.htfTrend });
    return rows.length > 0 ? rows : [{ label: "យុទ្ធសាស្ត្រ", value: "BBMA" }];
  }
  const ema9 = fmtNum(ind.ema9, 2);
  const ema21 = fmtNum(ind.ema21, 2);
  const rsi = fmtNum(ind.rsi, 1);
  const macd = fmtNum(ind.macdHist, 4);
  if (ema9) rows.push({ label: "EMA 9", value: ema9 });
  if (ema21) rows.push({ label: "EMA 21", value: ema21 });
  if (rsi) rows.push({ label: "RSI", value: rsi });
  if (macd) rows.push({ label: "MACD hist", value: macd });
  const adx = fmtNum(ind.adx, 1);
  if (adx) rows.push({ label: "ADX", value: adx });
  if (ind.htfTrend) rows.push({ label: "និន្នាការ HTF", value: ind.htfTrend });
  return rows.length > 0 ? rows : [{ label: "សូចនាករ", value: "—" }];
}

function DirectionPill({ direction }: { direction: Signal["direction"] }) {
  const isLong = direction === "long";
  return (
    <span
      className={`inline-flex items-center rounded-md px-2 py-0.5 font-mono text-[11px] font-semibold uppercase tracking-wide ${
        isLong ? "bg-long-soft text-long" : "bg-short-soft text-short"
      }`}
    >
      {isLong ? "ទិញ" : "លក់"}
    </span>
  );
}

function StatusPill({
  status,
  closedAt,
}: {
  status: Signal["status"];
  closedAt?: string | null;
}) {
  if (status === "open") {
    return (
      <span className="inline-flex items-center rounded-md bg-line px-2 py-0.5 font-mono text-[11px] font-medium tracking-wide text-slate">
        កំពុងបើក
      </span>
    );
  }
  if (status === "expired") {
    return (
      <span className="inline-flex items-center rounded-md bg-line px-2 py-0.5 font-mono text-[11px] font-semibold uppercase tracking-wide text-slate">
        ផុតកំណត់
      </span>
    );
  }
  if ((status === "tp1_hit" || status === "tp2_hit") && !closedAt) {
    return (
      <span className="inline-flex items-center rounded-md bg-accent-soft px-2 py-0.5 font-mono text-[11px] font-semibold uppercase tracking-wide text-accent">
        {status === "tp1_hit" ? "TP1 ប៉ះ" : "TP2 ប៉ះ"}
      </span>
    );
  }
  const label =
    status === "tp3_hit"
      ? "TP3 ប៉ះ"
      : status === "tp2_hit"
        ? "TP2 ប៉ះ"
        : status === "tp1_hit"
          ? "TP1 ប៉ះ"
          : status === "tp_hit"
            ? "TP ប៉ះ"
            : "SL ប៉ះ";
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
  showLlmBadge = false,
  showWarRoomBadge = false,
}: {
  signal: Signal;
  onSelect?: (signal: Signal) => void;
  adminSlot?: React.ReactNode;
  showLlmBadge?: boolean;
  showWarRoomBadge?: boolean;
}) {
  const isLong = signal.direction === "long";
  // Pure SL only — closed TP1/TP2 wins are not losses.
  const isSlHit = signal.status === "sl_hit";
  const Component = onSelect ? "button" : "div";

  return (
    <Component
      type={onSelect ? "button" : undefined}
      onClick={onSelect ? () => onSelect(signal) : undefined}
      className={`group relative w-full overflow-hidden rounded-lg border border-line bg-card text-left transition-colors hover:border-ink/25 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ink focus-visible:ring-offset-2 focus-visible:ring-offset-paper ${
        isSlHit ? "opacity-60 grayscale hover:opacity-80" : ""
      }`}
    >
      <div
        className={`absolute bottom-0 left-0 top-0 w-1 ${isLong ? "bg-long" : "bg-short"}`}
      />

      <div className="relative flex items-start justify-between gap-3 p-5 pb-4 pl-6">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-lg font-bold tracking-tight text-ink">
              {signal.symbol}
            </span>
            <DirectionPill direction={signal.direction} />
            {showLlmBadge ? (
              <span className="rounded-md bg-accent-soft px-2 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-wider text-accent">
                LLM
              </span>
            ) : null}
            {showWarRoomBadge ? (
              <span className="rounded-md bg-accent-soft px-2 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-wider text-accent">
                War Room
              </span>
            ) : null}
          </div>
          <div className="mt-2 flex items-center gap-2">
            <span className="rounded-md bg-accent/10 px-2 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-wider text-accent border border-accent/20">
              {formatTimeframe(signal.timeframe)}
            </span>
            <StatusPill status={signal.status} closedAt={signal.closedAt} />
          </div>
        </div>
        <div className="flex flex-col items-end justify-center pt-1">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-slate/70 mb-1.5">ទំនុកចិត្ត</p>
          <ConfidenceBar value={signal.confidence} compact />
        </div>
      </div>

      <div className="relative grid grid-cols-3 gap-3 border-t border-line/50 px-6 py-4 bg-slate/5">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-wider text-slate/70 mb-1">ចូល</p>
          <p className="font-mono text-sm font-bold text-ink">
            {formatPrice(signal.entry)}
          </p>
        </div>
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-wider text-slate/70 mb-1">បញ្ឈប់ខាត</p>
          <p className="font-mono text-sm font-bold text-short drop-shadow-sm">
            {formatPrice(signal.stopLoss)}
          </p>
        </div>
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-wider text-slate/70 mb-1">TP1 / TP2 / TP3</p>
          <p className="font-mono text-sm font-bold text-long drop-shadow-sm">
            {formatPrice(signal.takeProfit)}
            {signal.takeProfit2 != null ? ` / ${formatPrice(signal.takeProfit2)}` : ""}
            {signal.takeProfit3 != null ? ` / ${formatPrice(signal.takeProfit3)}` : ""}
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
            មើលព័ត៌មានលម្អិត{" "}
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
        aria-label="បិទប្រអប់"
        className="absolute inset-0 bg-black/50 backdrop-blur-[2px]"
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
                {formatTimeframe(signal.timeframe)}
              </span>
              <StatusPill status={signal.status} closedAt={signal.closedAt} />
            </div>
            <p className="mt-1 text-sm text-slate">
              បើក {formatDateTime(signal.createdAt)}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="btn-ghost shrink-0 rounded-lg p-2"
            aria-label="បិទ"
          >
            <CloseIcon />
          </button>
        </div>

        <div className="overflow-y-auto px-5 py-5">
          <div className="mb-5">
            <p className="mb-2 text-xs font-medium uppercase tracking-wide text-slate">
              ទំនុកចិត្ត
            </p>
            <ConfidenceBar value={signal.confidence} />
          </div>

          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <DetailRow label="ចូល" value={formatPrice(signal.entry)} />
            <DetailRow label="បញ្ឈប់ខាត" value={formatPrice(signal.stopLoss)} tone="short" />
            <DetailRow label="គោលដៅ 1" value={formatPrice(signal.takeProfit)} tone="long" />
            {signal.takeProfit2 != null ? (
              <DetailRow label="គោលដៅ 2" value={formatPrice(signal.takeProfit2)} tone="long" />
            ) : null}
            {signal.takeProfit3 != null ? (
              <DetailRow label="គោលដៅ 3" value={formatPrice(signal.takeProfit3)} tone="long" />
            ) : null}
            <DetailRow label="ហានិភ័យ / រង្វាន់" value={riskReward(signal)} tone="accent" />
          </div>

          {signal.chartUrl && (
            <div className="mt-4">
              <p className="text-[10px] font-semibold uppercase tracking-wider text-slate/70 mb-1">
                គំនូសតាងការរៀបចំ
              </p>
              <img
                src={signal.chartUrl}
                alt={`${signal.symbol} ${signal.timeframe} ${signal.direction} setup`}
                loading="lazy"
                className="w-full rounded-lg border border-slate/15"
              />
            </div>
          )}

          {signal.outcomeChartUrl && (
            <div className="mt-4">
              <p className="text-[10px] font-semibold uppercase tracking-wider text-slate/70 mb-1">
                លទ្ធផល
              </p>
              <img
                src={signal.outcomeChartUrl}
                alt={`${signal.symbol} ${signal.timeframe} ${signal.direction} outcome`}
                loading="lazy"
                className="w-full rounded-lg border border-slate/15"
              />
            </div>
          )}

          <div className="mt-5 rounded-lg border border-line bg-accent-soft/30 p-4">
            <p className="text-xs font-medium uppercase tracking-wide text-slate">
              ហេតុផល AI
            </p>
            <p className="mt-2 text-sm leading-relaxed text-ink">{signal.rationale}</p>
          </div>

          <SignalWarRoomSection signalId={signal.id} />

          <div className="mt-5">
            <p className="mb-3 text-xs font-medium uppercase tracking-wide text-slate">
              សូចនាករ
            </p>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {indicatorRows(signal).map((row) => (
                <DetailRow key={row.label} label={row.label} value={row.value} />
              ))}
            </div>
          </div>

          {signal.newsHeadlines.length > 0 ? (
            <div className="mt-5">
              <p className="mb-3 text-xs font-medium uppercase tracking-wide text-slate">
                ព័ត៌មានបានពិនិត្យ ({signal.newsHeadlines.length})
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

export function SignalsGrid({
  signals,
  showWarRoomBadge = false,
}: {
  signals: Signal[];
  showWarRoomBadge?: boolean;
}) {
  const [selected, setSelected] = useState<Signal | null>(null);

  return (
    <>
      <div className="grid w-full gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5">
        {signals.map((signal) => (
          <SignalCard
            key={signal.id}
            signal={signal}
            onSelect={setSelected}
            showWarRoomBadge={showWarRoomBadge}
          />
        ))}
      </div>
      {selected ? (
        <SignalDetailModal signal={selected} onClose={() => setSelected(null)} />
      ) : null}
    </>
  );
}
