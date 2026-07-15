import { formatRelativeTime } from "@/lib/format";
import { FLOOR_DESKS, type FloorBrief, type FloorDesk, type FloorTone } from "@/lib/floor/types";

const DESK_LABELS: Record<FloorDesk, string> = {
  macro: "Macro",
  technical: "Technical",
  news: "News",
  pm: "PM",
};

const TONE_STYLES: Record<FloorTone, string> = {
  bullish: "border-accent/30 bg-accent-soft text-accent",
  neutral: "border-line bg-paper text-slate",
  cautious: "border-line bg-paper text-ink",
};

export function DeskBoard({
  desks,
  isLoading = false,
}: {
  desks: FloorBrief[];
  isLoading?: boolean;
}) {
  if (desks.length === 0) {
    return (
      <section className="rounded-xl border border-dashed border-line bg-card p-10 text-center">
        <h2 className="text-base font-semibold text-ink">
          {isLoading ? "Loading desk board..." : "Desks warming up"}
        </h2>
        {isLoading ? null : (
          <p className="mt-1 text-sm text-slate">
            The floor cron has not posted yet.
          </p>
        )}
      </section>
    );
  }

  const deskByName = new Map(desks.map((brief) => [brief.desk, brief]));

  return (
    <section aria-label="Trading desk board" className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      {FLOOR_DESKS.map((desk) => {
        const brief = deskByName.get(desk);

        return (
          <article key={desk} className="flex min-h-44 flex-col rounded-xl border border-line bg-card p-5">
            <div className="flex items-center justify-between gap-3">
              <h2 className="text-sm font-semibold text-ink">{DESK_LABELS[desk]}</h2>
              {brief ? (
                <span
                  className={`rounded-md border px-2 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-wide ${TONE_STYLES[brief.tone]}`}
                >
                  {brief.tone}
                </span>
              ) : null}
            </div>
            <p className="mt-4 flex-1 text-sm leading-6 text-slate">{brief?.body ?? "—"}</p>
            {brief ? (
              <time className="mt-4 font-mono text-[11px] text-slate" dateTime={brief.createdAt}>
                {formatRelativeTime(brief.createdAt)}
              </time>
            ) : null}
          </article>
        );
      })}
    </section>
  );
}
