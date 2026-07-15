import { formatRelativeTime } from "@/lib/format";
import { FLOOR_DESKS, type FloorBrief, type FloorDesk, type FloorTone } from "@/lib/floor/types";
import { FloorRobot } from "./FloorRobot";

const DESK_LABELS: Record<FloorDesk, string> = {
  macro: "Macro",
  technical: "Technical",
  news: "News",
  pm: "PM",
};

const DESK_ROLES: Record<FloorDesk, string> = {
  macro: "Session + calendar",
  technical: "Structure + book",
  news: "Catalyst scan",
  pm: "Floor synthesis",
};

const TONE_STYLES: Record<FloorTone, string> = {
  bullish: "border-emerald-500/40 bg-emerald-500/15 text-emerald-700 dark:text-emerald-300",
  neutral: "border-line bg-paper text-slate",
  cautious: "border-amber-500/40 bg-amber-500/15 text-amber-800 dark:text-amber-200",
};

function robotMode(
  isLoading: boolean,
  hasBrief: boolean,
): "idle" | "working" | "warming" {
  if (isLoading) return "warming";
  if (hasBrief) return "working";
  return "idle";
}

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
    <section aria-label="Trading desk board" className="floor-pit overflow-hidden rounded-2xl border border-line">
      <div className="floor-pit__header flex flex-wrap items-center justify-between gap-3 border-b border-line px-4 py-3 sm:px-5">
        <div>
          <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-slate">Qauntify pit</p>
          <h2 className="text-base font-semibold text-ink">Live Trading Floor</h2>
        </div>
        <div className="flex items-center gap-3">
          <span className="floor-pit__live-dot" aria-hidden />
          <span className="font-mono text-xs text-slate">
            {isLoading
              ? "Booting desks..."
              : liveCount === 0
                ? "Waiting for cron"
                : `${liveCount}/4 desks posting`}
          </span>
        </div>
      </div>

      <div className="floor-pit__ticker" aria-hidden>
        <div className="floor-pit__ticker-track">
          <span>MACRO SCAN</span>
          <span>TECHNICAL BOOK</span>
          <span>NEWS WIRE</span>
          <span>PM RISK DESK</span>
          <span>FLOOR OPEN</span>
          <span>MACRO SCAN</span>
          <span>TECHNICAL BOOK</span>
          <span>NEWS WIRE</span>
          <span>PM RISK DESK</span>
          <span>FLOOR OPEN</span>
        </div>
      </div>

      <div className="floor-pit__grid grid gap-3 p-3 sm:p-4 md:grid-cols-2 xl:grid-cols-4">
        {FLOOR_DESKS.map((desk) => {
          const brief = deskByName.get(desk);
          const mode = robotMode(isLoading, Boolean(brief));

          return (
            <article
              key={desk}
              className="floor-station flex min-h-72 flex-col rounded-xl border border-line bg-card/90 p-4 backdrop-blur-sm"
            >
              <div className="flex items-start justify-between gap-2">
                <div>
                  <h3 className="text-sm font-semibold text-ink">{DESK_LABELS[desk]}</h3>
                  <p className="font-mono text-[10px] uppercase tracking-wide text-slate">
                    {DESK_ROLES[desk]}
                  </p>
                </div>
                {brief ? (
                  <span
                    className={`rounded-md border px-2 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-wide ${TONE_STYLES[brief.tone]}`}
                  >
                    {brief.tone}
                  </span>
                ) : (
                  <span className="rounded-md border border-dashed border-line px-2 py-0.5 font-mono text-[10px] uppercase tracking-wide text-slate">
                    {isLoading ? "boot" : "idle"}
                  </span>
                )}
              </div>

              <div className="floor-station__stage my-3 flex flex-1 items-end justify-center">
                <FloorRobot desk={desk} tone={brief?.tone} mode={mode} />
              </div>

              <p className="min-h-16 text-sm leading-6 text-slate">
                {isLoading
                  ? "Robot is warming systems..."
                  : brief?.body ?? "Standing by for the next floor run."}
              </p>
              {brief ? (
                <time
                  className="mt-3 font-mono text-[11px] text-slate"
                  dateTime={brief.createdAt}
                >
                  {formatRelativeTime(brief.createdAt)}
                </time>
              ) : (
                <p className="mt-3 font-mono text-[11px] text-slate">
                  {isLoading ? "syncing..." : "no brief yet"}
                </p>
              )}
            </article>
          );
        })}
      </div>
    </section>
  );
}
