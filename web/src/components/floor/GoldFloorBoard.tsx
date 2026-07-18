"use client";

import { useEffect, useRef } from "react";

import { formatRelativeTime } from "@/lib/format";
import type { FloorGoldSignal, FloorLogEntry, FloorRunPhase } from "@/lib/floor/types";

const DESK_COLOUR: Record<string, string> = {
  macro: "text-blue-400",
  technical: "text-teal-400",
  news: "text-slate",
  pm: "text-amber-400",
  system: "text-accent",
};

const TONE_DOT: Record<string, string> = {
  bullish: "bg-long",
  cautious: "bg-short",
  neutral: "bg-slate",
};

function StreamLine({ entry, index }: { entry: FloorLogEntry; index: number }) {
  const colour = DESK_COLOUR[entry.desk] ?? "text-slate";
  const dot = TONE_DOT[entry.tone] ?? "bg-slate";

  return (
    <div
      className="floor-stream-line"
      style={{ animationDelay: `${Math.min(index * 0.04, 0.6)}s` }}
    >
      <span className={`floor-stream-dot ${dot}`} aria-hidden="true" />
      <span className={`floor-stream-desk ${colour}`}>
        {entry.desk.toUpperCase().slice(0, 4)}
      </span>
      <span className="floor-stream-sep" aria-hidden="true">|</span>
      <span className="floor-stream-text">{entry.text}</span>
      <time
        className="floor-stream-time"
        dateTime={entry.ts}
        title={new Date(entry.ts).toLocaleTimeString()}
      >
        {new Date(entry.ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
      </time>
    </div>
  );
}

function GoldSignalCard({ signal, symbol }: { signal: FloorGoldSignal; symbol: string }) {
  const directionStyle = signal.direction === "long"
    ? "border-long/40 bg-long-soft"
    : "border-short/40 bg-short-soft";
  const dirLabel = signal.direction === "long" ? "text-long" : "text-short";

  return (
    <article className={`rounded-2xl border p-5 ${directionStyle}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h4 className="text-base font-semibold text-ink">{symbol} — AI signal</h4>
        <span className={`text-sm font-bold uppercase tracking-wide ${dirLabel}`}>
          {signal.direction}
        </span>
      </div>
      <dl className="mt-4 grid grid-cols-2 gap-x-6 gap-y-3 text-sm">
        <div>
          <dt className="text-slate">Entry</dt>
          <dd className="font-mono font-semibold text-ink">{signal.entry}</dd>
        </div>
        <div>
          <dt className="text-slate">Confidence</dt>
          <dd className="font-mono font-semibold text-ink">{signal.confidence}%</dd>
        </div>
        <div>
          <dt className="text-slate">Stop loss</dt>
          <dd className="font-mono font-semibold text-ink">{signal.stopLoss}</dd>
        </div>
        <div>
          <dt className="text-slate">Take profit</dt>
          <dd className="font-mono font-semibold text-ink">{signal.takeProfit}</dd>
        </div>
      </dl>
      <p className="mt-4 text-sm leading-6 text-ink">{signal.body}</p>
      <time className="mt-3 block font-mono text-xs text-slate" dateTime={signal.createdAt}>
        {formatRelativeTime(signal.createdAt)}
      </time>
    </article>
  );
}

export function GoldFloorBoard({
  symbol,
  log,
  lastSignal,
  scanLine,
  isLoading = false,
  isHunting = false,
  phase = "idle",
}: {
  symbol: string;
  log: FloorLogEntry[];
  lastSignal: FloorGoldSignal | null;
  scanLine: string;
  isLoading?: boolean;
  isHunting?: boolean;
  phase?: FloorRunPhase;
}) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [log.length]);

  const isEmpty = log.length === 0;
  const statusLine = isLoading
    ? "Loading..."
    : isHunting
      ? phase === "sleeping"
        ? "Cooling down before next cycle..."
        : `${phase.toUpperCase()} desk thinking...`
      : scanLine;

  return (
    <div className="w-full min-w-0 space-y-6">
      <section className="rounded-2xl border border-line bg-card p-5">
        <div className="flex flex-wrap items-end justify-between gap-2">
          <div>
            <h2 className="text-lg font-semibold text-ink">Gold floor — {symbol}</h2>
            <p className="mt-1 text-sm text-slate">
              Four AI desks stream their analysis live. The PM drops a signal or passes each cycle.
            </p>
          </div>
          <p className="font-mono text-xs text-slate">{statusLine}</p>
        </div>
      </section>

      <section aria-label="AI stream" className="w-full min-w-0 space-y-2">
        <h3 className="text-base font-semibold text-ink">Live AI stream</h3>
        <div className="floor-stream-panel" aria-live="polite" aria-atomic="false">
          {isEmpty ? (
            <p className="floor-stream-empty">
              {isHunting
                ? "Waiting for the first desk response..."
                : "Press Run — the AI stream will appear here in real time."}
            </p>
          ) : (
            [...log].reverse().map((entry, i) => (
              <StreamLine key={`${entry.ts}-${i}`} entry={entry} index={i} />
            ))
          )}
          <div ref={bottomRef} />
        </div>
      </section>

      <section aria-label="Latest AI signal" className="w-full min-w-0 space-y-2">
        <h3 className="text-base font-semibold text-ink">Latest AI signal</h3>
        {lastSignal ? (
          <GoldSignalCard signal={lastSignal} symbol={symbol} />
        ) : (
          <div className="rounded-2xl border border-dashed border-line bg-card p-8 text-center">
            <p className="text-sm font-semibold text-ink">No signal yet</p>
            <p className="mt-1 text-sm text-slate">
              The PM desk drops a trade when conviction is high, or passes each cycle.
            </p>
          </div>
        )}
      </section>
    </div>
  );
}
