"use client";

import { formatRelativeTime } from "@/lib/format";
import {
  FLOOR_DESKS,
  type FloorBrief,
  type FloorDesk,
  type FloorGoldSignal,
  type FloorRunPhase,
  type FloorTone,
} from "@/lib/floor/types";
import { deskHuntState } from "./FloorRobot";

const DESK_LABELS: Record<FloorDesk, string> = {
  macro: "Macro desk",
  technical: "Technical desk",
  news: "News desk",
  pm: "PM desk",
};

const TONE_STYLES: Record<FloorTone, string> = {
  bullish: "bg-long-soft text-long",
  neutral: "bg-paper text-slate border border-line",
  cautious: "bg-short-soft text-short",
};

const STANDBY_COPY = "Waiting for the next AI cycle. Press Run to start hunting.";

function GoldSignalCard({ signal, symbol }: { signal: FloorGoldSignal; symbol: string }) {
  const directionStyle = signal.direction === "long"
    ? "bg-long-soft text-long"
    : "bg-short-soft text-short";

  return (
    <article className="rounded-2xl border border-line bg-card p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h4 className="text-base font-semibold text-ink">
          {symbol} — AI signal
        </h4>
        <span className={`rounded-md px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide ${directionStyle}`}>
          {signal.direction}
        </span>
      </div>
      <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
        <div>
          <dt className="text-slate">Entry</dt>
          <dd className="font-mono font-medium text-ink">{signal.entry}</dd>
        </div>
        <div>
          <dt className="text-slate">Confidence</dt>
          <dd className="font-mono font-medium text-ink">{signal.confidence}%</dd>
        </div>
        <div>
          <dt className="text-slate">Stop loss</dt>
          <dd className="font-mono font-medium text-ink">{signal.stopLoss}</dd>
        </div>
        <div>
          <dt className="text-slate">Take profit</dt>
          <dd className="font-mono font-medium text-ink">{signal.takeProfit}</dd>
        </div>
      </dl>
      <p className="mt-4 text-sm leading-6 text-ink">{signal.body}</p>
      <time className="mt-4 block font-mono text-xs text-slate" dateTime={signal.createdAt}>
        {formatRelativeTime(signal.createdAt)}
      </time>
    </article>
  );
}

export function GoldFloorBoard({
  symbol,
  desks,
  lastSignal,
  scanLine,
  isLoading = false,
  isHunting = false,
  phase = "idle",
}: {
  symbol: string;
  desks: FloorBrief[];
  lastSignal: FloorGoldSignal | null;
  scanLine: string;
  isLoading?: boolean;
  isHunting?: boolean;
  phase?: FloorRunPhase;
}) {
  const deskByName = new Map(desks.map((brief) => [brief.desk, brief]));

  return (
    <div className="w-full min-w-0 space-y-6">
      <section className="rounded-2xl border border-line bg-card p-5">
        <div className="flex flex-wrap items-end justify-between gap-2">
          <div>
            <h2 className="text-lg font-semibold text-ink">Gold floor — {symbol}</h2>
            <p className="mt-1 text-sm text-slate">
              Independent AI desks hunt PAXG. The PM decides signal or pass — no engine reuse.
            </p>
          </div>
          <p className="font-mono text-xs text-slate">
            {isLoading ? "Loading..." : isHunting ? "Hunting..." : scanLine}
          </p>
        </div>
      </section>

      <section aria-label="Desk briefs" className="w-full min-w-0 space-y-4">
        <h3 className="text-base font-semibold text-ink">Desk briefs</h3>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {FLOOR_DESKS.map((desk) => {
            const brief = deskByName.get(desk);
            const hunt = isHunting ? deskHuntState(desk, phase) : "waiting";

            return (
              <article
                key={desk}
                className={[
                  "floor-desk-card flex min-w-0 flex-col rounded-2xl border border-line bg-card p-5",
                  isHunting ? `floor-desk-card--${hunt}` : "",
                ].join(" ")}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <h4 className="text-base font-semibold text-ink">{DESK_LABELS[desk]}</h4>
                    {isHunting ? (
                      <p className="mt-1 font-mono text-[11px] uppercase tracking-wide text-slate">
                        {hunt === "active" && "Analyzing now"}
                        {hunt === "done" && "Brief locked"}
                        {hunt === "waiting" && "Queued"}
                        {hunt === "sleeping" && "Cooldown"}
                      </p>
                    ) : null}
                  </div>
                  {brief ? (
                    <span
                      className={`shrink-0 rounded-md px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide ${TONE_STYLES[brief.tone]}`}
                    >
                      {brief.tone}
                    </span>
                  ) : (
                    <span className="shrink-0 rounded-md border border-dashed border-line px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide text-slate">
                      {isLoading ? "Loading" : isHunting && hunt === "active" ? "Live" : "Standby"}
                    </span>
                  )}
                </div>

                <p className="mt-4 min-h-16 flex-1 whitespace-pre-wrap text-sm leading-6 text-ink">
                  {isLoading
                    ? "Loading desk brief..."
                    : isHunting && hunt === "active" && !brief
                      ? "Desk is reading market context..."
                      : brief?.body ?? STANDBY_COPY}
                </p>

                {isHunting && hunt === "active" ? (
                  <div className="floor-desk-shimmer mt-4" aria-hidden="true" />
                ) : null}

                {brief ? (
                  <time
                    className="mt-4 font-mono text-xs text-slate"
                    dateTime={brief.createdAt}
                  >
                    {formatRelativeTime(brief.createdAt)}
                  </time>
                ) : null}
              </article>
            );
          })}
        </div>
      </section>

      <section aria-label="Gold signals" className="w-full min-w-0 space-y-4">
        <h3 className="text-base font-semibold text-ink">Latest AI signal</h3>
        {lastSignal ? (
          <GoldSignalCard signal={lastSignal} symbol={symbol} />
        ) : (
          <div className="rounded-2xl border border-dashed border-line bg-card p-8 text-center">
            <p className="text-sm font-semibold text-ink">No AI signal yet</p>
            <p className="mt-1 text-sm text-slate">
              The PM desk will drop a trade when conviction is high, or pass each cycle until you stop.
            </p>
          </div>
        )}
      </section>
    </div>
  );
}
