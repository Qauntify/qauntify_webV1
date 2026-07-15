import { formatRelativeTime } from "@/lib/format";
import { FLOOR_DESKS, type FloorBrief, type FloorDesk, type FloorTone } from "@/lib/floor/types";
import { TradingConsole } from "./TradingConsole";

const DESK_LABELS: Record<FloorDesk, string> = {
  macro: "Macro desk",
  technical: "Technical desk",
  news: "News desk",
  pm: "PM / Risk",
};

const DESK_ROLES: Record<FloorDesk, string> = {
  macro: "Session + calendar",
  technical: "Structure + open book",
  news: "Catalyst wire",
  pm: "Floor synthesis",
};

const TONE_STYLES: Record<FloorTone, string> = {
  bullish: "border-emerald-400/40 bg-emerald-500/20 text-emerald-200",
  neutral: "border-white/15 bg-white/5 text-slate-200",
  cautious: "border-amber-400/40 bg-amber-500/20 text-amber-100",
};

export function DeskBoard({
  desks,
  isLoading = false,
}: {
  desks: FloorBrief[];
  isLoading?: boolean;
}) {
  const deskByName = new Map(desks.map((brief) => [brief.desk, brief]));
  const liveCount = desks.length;

  return (
    <section aria-label="Trading desk board" className="dealing-room overflow-hidden rounded-2xl border border-line">
      <div className="dealing-room__skyline" aria-hidden>
        <div className="dealing-room__wall-glow" />
        <div className="dealing-room__desk-rows">
          <span />
          <span />
          <span />
        </div>
        <div className="dealing-room__screen-haze" />
      </div>

      <div className="relative z-[1]">
        <div className="dealing-room__header flex flex-wrap items-center justify-between gap-3 border-b border-white/10 px-4 py-3 sm:px-5">
          <div>
            <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-cyan-200/70">
              Dealing room
            </p>
            <h2 className="text-base font-semibold text-white">Institutional Trading Floor</h2>
          </div>
          <div className="flex items-center gap-3">
            <span className="dealing-room__live" aria-hidden />
            <span className="font-mono text-xs text-slate-300">
              {isLoading
                ? "Connecting consoles..."
                : liveCount === 0
                  ? "Desks on standby"
                  : `${liveCount}/4 desks live`}
            </span>
          </div>
        </div>

        <div className="dealing-room__ticker" aria-hidden>
          <div className="dealing-room__ticker-track">
            <span>EURUSD +0.12</span>
            <span>GBPUSD -0.08</span>
            <span>XAUUSD +0.34</span>
            <span>BTCUSDT RANGE</span>
            <span>LONDON OPEN</span>
            <span>NY RISK WINDOW</span>
            <span>MACRO DESK ACTIVE</span>
            <span>PM SYNC</span>
            <span>EURUSD +0.12</span>
            <span>GBPUSD -0.08</span>
            <span>XAUUSD +0.34</span>
            <span>BTCUSDT RANGE</span>
            <span>LONDON OPEN</span>
            <span>NY RISK WINDOW</span>
            <span>MACRO DESK ACTIVE</span>
            <span>PM SYNC</span>
          </div>
        </div>

        <div className="grid gap-3 p-3 sm:p-4 md:grid-cols-2 xl:grid-cols-4">
          {FLOOR_DESKS.map((desk) => {
            const brief = deskByName.get(desk);
            const active = Boolean(brief) || isLoading;

            return (
              <article
                key={desk}
                className="dealing-desk flex min-h-72 flex-col border border-white/10 bg-black/35 p-4 backdrop-blur-md"
              >
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <h3 className="text-sm font-semibold text-white">{DESK_LABELS[desk]}</h3>
                    <p className="font-mono text-[10px] uppercase tracking-wide text-slate-400">
                      {DESK_ROLES[desk]}
                    </p>
                  </div>
                  {brief ? (
                    <span
                      className={`rounded border px-2 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-wide ${TONE_STYLES[brief.tone]}`}
                    >
                      {brief.tone}
                    </span>
                  ) : (
                    <span className="rounded border border-dashed border-white/20 px-2 py-0.5 font-mono text-[10px] uppercase tracking-wide text-slate-400">
                      {isLoading ? "sync" : "standby"}
                    </span>
                  )}
                </div>

                <div className="dealing-desk__console my-3 flex flex-1 items-center justify-center">
                  <TradingConsole desk={desk} active={active} />
                </div>

                <p className="min-h-16 text-sm leading-6 text-slate-300">
                  {isLoading
                    ? "Pulling feeds across the monitor bank..."
                    : brief?.body ?? "Console on standby for the next floor run."}
                </p>
                {brief ? (
                  <time
                    className="mt-3 font-mono text-[11px] text-slate-500"
                    dateTime={brief.createdAt}
                  >
                    {formatRelativeTime(brief.createdAt)}
                  </time>
                ) : (
                  <p className="mt-3 font-mono text-[11px] text-slate-500">
                    {isLoading ? "syncing..." : "awaiting brief"}
                  </p>
                )}
              </article>
            );
          })}
        </div>
      </div>
    </section>
  );
}
