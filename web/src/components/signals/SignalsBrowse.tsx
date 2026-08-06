import { SignalsGrid } from "@/components/dashboard/SignalsGrid";
import { Pagination } from "@/components/shared/Pagination";
import { SignalsBrowseFilter } from "@/components/signals/SignalsBrowseFilter";
import { SignalsSessionRail } from "@/components/signals/SignalsSessionRail";
import { SignalsStatsStrip } from "@/components/signals/SignalsStatsStrip";
import {
  getSignals,
  getStats,
  getWarRoomSignalsPaginated,
  type SignalLane,
} from "@/lib/signals";
import {
  SIGNAL_FILTER_OPTIONS,
  type SignalsBrowseTab,
} from "@/lib/signals-browse-tabs";

export type { SignalsBrowseTab };
export { parseSignalsBrowseTab } from "@/lib/signals-browse-tabs";

const SESSIONS = [
  {
    id: "super-scalping" as const,
    title: "Super scalping",
    subtitle: "5m ICT — sweep, CHoCH, FVG retest",
    timeframe: "5m",
    lane: "default" as SignalLane,
    code: "5M",
    emptyHint: "Setups fire on each 5m close (cron backup ~10m).",
  },
  {
    id: "scalping" as const,
    title: "Scalping",
    subtitle: "15m cloud rejection + CHoCH",
    timeframe: "15m",
    lane: "default" as SignalLane,
    code: "15M",
    emptyHint: "Setups fire on each 15m close (cron backup ~10m).",
  },
  {
    id: "swing" as const,
    title: "Swing",
    subtitle: "1h AI-confirmed conviction",
    timeframe: "1h",
    lane: "default" as SignalLane,
    code: "1H",
    emptyHint: "Setups fire on each 1h close (cron backup ~10m).",
  },
  {
    id: "bbma" as const,
    title: "BBMA",
    subtitle: "XAU H1 taught BBMA — live EA, no AI gate",
    timeframe: "bbma",
    lane: "bbma" as SignalLane,
    code: "BBMA",
    emptyHint: "New setups publish on each H1 close from the MT5 EA.",
  },
];

async function LanePanel({
  title,
  subtitle,
  code,
  timeframe,
  lane,
  emptyHint,
  accessToken,
  embedded = false,
}: {
  title: string;
  subtitle: string;
  code: string;
  timeframe: string;
  lane: SignalLane;
  emptyHint: string;
  accessToken: string | undefined;
  /** Inside the combined desk card — no second outer frame. */
  embedded?: boolean;
}) {
  const [signals, stats] = await Promise.all([
    getSignals(30, accessToken, timeframe === "bbma" ? undefined : timeframe, lane),
    getStats(accessToken, timeframe === "bbma" ? "bbma" : timeframe, lane),
  ]);

  const inner = (
    <>
      <header className="flex flex-wrap items-end justify-between gap-3 border-b border-line px-5 py-4 sm:px-6">
        <div className="flex min-w-0 items-start gap-3">
          <span className="mt-0.5 inline-flex h-9 min-w-12 items-center justify-center rounded-md bg-ink px-2 font-mono text-xs font-bold tracking-[0.12em] text-paper">
            {code}
          </span>
          <div className="min-w-0">
            <h2 className="text-base font-bold tracking-tight text-ink sm:text-lg">
              {title}
            </h2>
            <p className="mt-0.5 text-xs text-slate sm:text-sm">{subtitle}</p>
          </div>
        </div>
        <div className="flex items-center gap-3 font-mono text-[11px] text-slate">
          <span className="rounded-md bg-paper px-2 py-1 ring-1 ring-inset ring-line">
            {signals.length} live in view
          </span>
          {stats.winRate !== null ? (
            <span className="rounded-md bg-long-soft px-2 py-1 font-semibold text-long">
              {stats.winRate}% WR
            </span>
          ) : null}
        </div>
      </header>

      <div className="space-y-5 p-5 sm:p-6">
        <SignalsStatsStrip stats={stats} />

        {signals.length > 0 ? (
          <SignalsGrid signals={signals} />
        ) : (
          <div className="rounded-lg border border-dashed border-line bg-paper/80 px-6 py-12 text-center">
            <p className="font-mono text-[10px] font-semibold tracking-[0.18em] text-slate">
              EMPTY LANE
            </p>
            <p className="mt-2 text-sm font-semibold text-ink">
              No {title.toLowerCase()} signals yet
            </p>
            <p className="mx-auto mt-1 max-w-sm text-xs text-slate">{emptyHint}</p>
          </div>
        )}
      </div>
    </>
  );

  if (embedded) {
    return <section className="signals-lane border-t border-line">{inner}</section>;
  }

  return (
    <section className="signals-lane overflow-hidden rounded-xl border border-line bg-card">
      {inner}
    </section>
  );
}

export async function SignalsBrowse({
  tab,
  page = 1,
  accessToken,
  basePath,
  hideFilter = false,
  desk = false,
}: {
  tab: SignalsBrowseTab;
  page?: number;
  accessToken?: string;
  basePath: string;
  hideFilter?: boolean;
  /** Trading-desk chrome (rail + lane panels). */
  desk?: boolean;
}) {
  const isWarRoomTab = tab === "war-room";
  const warRoomPage = isWarRoomTab
    ? await getWarRoomSignalsPaginated(page, accessToken)
    : null;

  const activeMeta =
    SIGNAL_FILTER_OPTIONS.find((o) => o.id === tab) ?? SIGNAL_FILTER_OPTIONS[0];

  const warRoomInner = warRoomPage ? (
    <>
      <header className="flex flex-wrap items-end justify-between gap-3 border-b border-line px-5 py-4 sm:px-6">
        <div className="flex min-w-0 items-start gap-3">
          <span className="mt-0.5 inline-flex h-9 min-w-12 items-center justify-center rounded-md bg-ink px-2 font-mono text-xs font-bold tracking-[0.12em] text-paper">
            WR
          </span>
          <div>
            <h2 className="text-base font-bold tracking-tight text-ink sm:text-lg">
              War Room
            </h2>
            <p className="mt-0.5 text-xs text-slate sm:text-sm">
              Floor-decided — not mixed with strategy lanes
            </p>
          </div>
        </div>
        <span className="font-mono text-[11px] text-slate">
          {warRoomPage.total} total
        </span>
      </header>
      <div className="p-5 sm:p-6">
        {warRoomPage.signals.length > 0 ? (
          <>
            <SignalsGrid signals={warRoomPage.signals} showWarRoomBadge />
            <Pagination
              page={warRoomPage.page}
              totalPages={warRoomPage.totalPages}
              total={warRoomPage.total}
              pageSize={warRoomPage.pageSize}
              basePath={basePath}
              extraParams={{ tab: "war-room" }}
            />
          </>
        ) : (
          <div className="rounded-lg border border-dashed border-line bg-paper/80 px-6 py-12 text-center">
            <p className="font-mono text-[10px] font-semibold tracking-[0.18em] text-slate">
              EMPTY LANE
            </p>
            <p className="mt-2 text-sm font-semibold text-ink">No War Room signals yet</p>
            <p className="mx-auto mt-1 max-w-sm text-xs text-slate">
              Floor-decided signals show up here — not strategy-tab trades.
            </p>
          </div>
        )}
      </div>
    </>
  ) : null;

  const content = isWarRoomTab && warRoomInner ? (
    desk ? (
      <div className="signals-lane border-t border-line">{warRoomInner}</div>
    ) : (
      <section className="signals-lane overflow-hidden rounded-xl border border-line bg-card">
        {warRoomInner}
      </section>
    )
  ) : tab === "all" ? (
    <>
      {SESSIONS.map((s) => (
        <LanePanel
          key={s.id}
          title={s.title}
          subtitle={s.subtitle}
          code={s.code}
          timeframe={s.timeframe}
          lane={s.lane}
          emptyHint={s.emptyHint}
          accessToken={accessToken}
          embedded={desk}
        />
      ))}
    </>
  ) : (
    <LanePanel
      accessToken={accessToken}
      title={SESSIONS.find((s) => s.id === tab)!.title}
      subtitle={SESSIONS.find((s) => s.id === tab)!.subtitle}
      code={SESSIONS.find((s) => s.id === tab)!.code}
      timeframe={SESSIONS.find((s) => s.id === tab)!.timeframe}
      lane={SESSIONS.find((s) => s.id === tab)!.lane}
      emptyHint={SESSIONS.find((s) => s.id === tab)!.emptyHint}
      embedded={desk}
    />
  );

  if (!desk) {
    return (
      <div className="w-full space-y-6">
        {hideFilter ? null : (
          <SignalsBrowseFilter tab={tab} basePath={basePath} />
        )}
        {tab === "all" ? (
          <div className="space-y-5">{content}</div>
        ) : (
          content
        )}
      </div>
    );
  }

  return (
    <div className="signals-desk w-full overflow-hidden rounded-xl border border-line bg-card">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-4 py-3 sm:px-5">
        <div className="flex items-center gap-2.5">
          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-long opacity-40" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-long" />
          </span>
          <p className="font-mono text-[11px] font-semibold tracking-[0.14em] text-slate">
            DESK · {activeMeta.code}
          </p>
        </div>
        <p className="font-mono text-[11px] text-slate">{activeMeta.hint}</p>
      </div>
      <div className="border-b border-line px-3 py-3 sm:px-4">
        <SignalsSessionRail tab={tab} basePath={basePath} />
      </div>
      {content}
    </div>
  );
}
