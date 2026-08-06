import { SignalsGrid } from "@/components/dashboard/SignalsGrid";
import { StatsBar } from "@/components/dashboard/StatsBar";
import { Pagination } from "@/components/shared/Pagination";
import { SignalsBrowseFilter } from "@/components/signals/SignalsBrowseFilter";
import { SignalsSessionRail } from "@/components/signals/SignalsSessionRail";
import {
  getSignals,
  getSignalsPaginated,
  getStats,
  getWarRoomSignalsPaginated,
  type SignalLane,
} from "@/lib/signals";
import type { SignalsBrowseTab } from "@/lib/signals-browse-tabs";

const ALL_PAGE_SIZE = 20;

export type { SignalsBrowseTab };
export { parseSignalsBrowseTab } from "@/lib/signals-browse-tabs";

const SESSIONS = [
  {
    id: "super-scalping" as const,
    title: "Super scalping",
    subtitle: "5m ICT — sweep, CHoCH, FVG retest",
    timeframe: "5m",
    lane: "default" as SignalLane,
    emptyHint: "Setups appear after each 5m close.",
  },
  {
    id: "scalping" as const,
    title: "Scalping",
    subtitle: "15m cloud rejection + CHoCH",
    timeframe: "15m",
    lane: "default" as SignalLane,
    emptyHint: "Setups appear after each 15m close.",
  },
  {
    id: "swing" as const,
    title: "Swing",
    subtitle: "1h AI-confirmed setups",
    timeframe: "1h",
    lane: "default" as SignalLane,
    emptyHint: "Setups appear after each 1h close.",
  },
  {
    id: "bbma" as const,
    title: "BBMA",
    subtitle: "XAU H1 — live MT5 EA, no AI gate",
    timeframe: "bbma",
    lane: "bbma" as SignalLane,
    emptyHint: "New setups publish on each H1 close from the EA.",
  },
];

async function SessionBlock({
  title,
  subtitle,
  timeframe,
  lane,
  emptyHint,
  accessToken,
}: {
  title: string;
  subtitle: string;
  timeframe: string;
  lane: SignalLane;
  emptyHint: string;
  accessToken: string | undefined;
}) {
  const [signals, stats] = await Promise.all([
    getSignals(30, accessToken, timeframe === "bbma" ? undefined : timeframe, lane),
    getStats(accessToken, timeframe === "bbma" ? "bbma" : timeframe, lane),
  ]);

  return (
    <section className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold tracking-tight text-ink">{title}</h2>
          <p className="mt-1 text-sm text-slate">{subtitle}</p>
        </div>
        {signals.length > 0 ? (
          <p className="text-sm text-slate">
            {signals.length} signal{signals.length === 1 ? "" : "s"}
          </p>
        ) : null}
      </div>

      <StatsBar stats={stats} />

      {signals.length > 0 ? (
        <SignalsGrid signals={signals} />
      ) : (
        <div className="rounded-xl border border-dashed border-line bg-card px-6 py-14 text-center">
          <p className="text-sm font-semibold text-ink">No {title.toLowerCase()} signals yet</p>
          <p className="mx-auto mt-1.5 max-w-sm text-sm text-slate">{emptyHint}</p>
        </div>
      )}
    </section>
  );
}

export async function SignalsBrowse({
  tab,
  page = 1,
  accessToken,
  basePath,
  hideFilter = false,
}: {
  tab: SignalsBrowseTab;
  page?: number;
  accessToken?: string;
  basePath: string;
  hideFilter?: boolean;
}) {
  const isWarRoomTab = tab === "war-room";
  const isAllTab = tab === "all";

  const [warRoomPage, allPage, allStats] = await Promise.all([
    isWarRoomTab ? getWarRoomSignalsPaginated(page, accessToken) : null,
    isAllTab
      ? getSignalsPaginated(page, accessToken, undefined, ALL_PAGE_SIZE)
      : null,
    isAllTab ? getStats(accessToken) : null,
  ]);

  return (
    <div className="w-full space-y-8">
      {hideFilter ? (
        <SignalsSessionRail tab={tab} basePath={basePath} />
      ) : (
        <SignalsBrowseFilter tab={tab} basePath={basePath} showLabel={false} compact />
      )}

      {isWarRoomTab && warRoomPage ? (
        <section className="space-y-5">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold tracking-tight text-ink">War Room</h2>
              <p className="mt-1 text-sm text-slate">
                Floor-decided setups — separate from strategy sessions
              </p>
            </div>
            {warRoomPage.total > 0 ? (
              <p className="text-sm text-slate">{warRoomPage.total} total</p>
            ) : null}
          </div>

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
            <div className="rounded-xl border border-dashed border-line bg-card px-6 py-14 text-center">
              <p className="text-sm font-semibold text-ink">No War Room signals yet</p>
              <p className="mx-auto mt-1.5 max-w-sm text-sm text-slate">
                Floor-decided signals will show up here.
              </p>
            </div>
          )}
        </section>
      ) : isAllTab && allPage && allStats ? (
        <section className="space-y-5">
          <StatsBar stats={allStats} />

          {allPage.signals.length > 0 ? (
            <>
              <SignalsGrid signals={allPage.signals} />
              <Pagination
                page={allPage.page}
                totalPages={allPage.totalPages}
                total={allPage.total}
                pageSize={allPage.pageSize}
                basePath={basePath}
              />
            </>
          ) : (
            <div className="rounded-xl border border-dashed border-line bg-card px-6 py-14 text-center">
              <p className="text-sm font-semibold text-ink">No signals yet</p>
              <p className="mx-auto mt-1.5 max-w-sm text-sm text-slate">
                New setups will show up here as sessions fire.
              </p>
            </div>
          )}
        </section>
      ) : (
        <SessionBlock
          accessToken={accessToken}
          title={SESSIONS.find((s) => s.id === tab)!.title}
          subtitle={SESSIONS.find((s) => s.id === tab)!.subtitle}
          timeframe={SESSIONS.find((s) => s.id === tab)!.timeframe}
          lane={SESSIONS.find((s) => s.id === tab)!.lane}
          emptyHint={SESSIONS.find((s) => s.id === tab)!.emptyHint}
        />
      )}
    </div>
  );
}
