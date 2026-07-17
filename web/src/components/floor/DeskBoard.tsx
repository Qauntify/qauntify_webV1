import { formatRelativeTime } from "@/lib/format";
import { FLOOR_DESKS, type FloorBrief, type FloorDesk, type FloorTone } from "@/lib/floor/types";

const DESK_LABELS: Record<FloorDesk, string> = {
  macro: "Macro",
  technical: "Technical",
  news: "News",
  pm: "PM / Risk",
};

const DESK_ROLES: Record<FloorDesk, string> = {
  macro: "Session and calendar context",
  technical: "Structure and open book",
  news: "Catalyst and headline risk",
  pm: "Floor synthesis and risk",
};

const TONE_STYLES: Record<FloorTone, string> = {
  bullish: "bg-long-soft text-long",
  neutral: "bg-paper text-slate border border-line",
  cautious: "bg-short-soft text-short",
};

const STANDBY_COPY = "No brief yet. Waiting for the next floor run.";

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
    <section aria-label="Trading desk board" className="w-full min-w-0 space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <p className="font-mono text-xs text-slate">
          {isLoading
            ? "Loading desks..."
            : liveCount === 0
              ? "Desks on standby"
              : `${liveCount}/4 desks live`}
        </p>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {FLOOR_DESKS.map((desk) => {
          const brief = deskByName.get(desk);

          return (
            <article
              key={desk}
              className="flex min-w-0 flex-col rounded-2xl border border-line bg-card p-5"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <h3 className="text-base font-semibold text-ink">{DESK_LABELS[desk]}</h3>
                  <p className="mt-0.5 text-xs text-slate">{DESK_ROLES[desk]}</p>
                </div>
                {brief ? (
                  <span
                    className={`shrink-0 rounded-md px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide ${TONE_STYLES[brief.tone]}`}
                  >
                    {brief.tone}
                  </span>
                ) : (
                  <span className="shrink-0 rounded-md border border-dashed border-line px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide text-slate">
                    {isLoading ? "Loading" : "Standby"}
                  </span>
                )}
              </div>

              <p className="mt-4 min-h-16 flex-1 text-sm leading-6 text-ink">
                {isLoading
                  ? "Loading desk brief..."
                  : brief?.body ?? STANDBY_COPY}
              </p>

              {brief ? (
                <time
                  className="mt-4 font-mono text-xs text-slate"
                  dateTime={brief.createdAt}
                >
                  {formatRelativeTime(brief.createdAt)}
                </time>
              ) : (
                <p className="mt-4 font-mono text-xs text-slate">
                  {isLoading ? "Syncing..." : "Awaiting brief"}
                </p>
              )}
            </article>
          );
        })}
      </div>
    </section>
  );
}
