import { SignalsGrid } from "@/components/dashboard/SignalsGrid";
import { StatsBar } from "@/components/dashboard/StatsBar";
import { AiStrategyRail } from "@/components/signals/AiStrategyRail";
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
import {
  parseAiSignalStrategy,
  type AiSignalStrategy,
  type SignalsBrowseTab,
} from "@/lib/signals-browse-tabs";

const ALL_PAGE_SIZE = 20;

export type { AiSignalStrategy, SignalsBrowseTab };
export { parseAiSignalStrategy, parseSignalsBrowseTab } from "@/lib/signals-browse-tabs";

const AI_STRATEGY_META: Record<
  Exclude<AiSignalStrategy, "all">,
  { title: string; subtitle: string; emptyHint: string; timeframe?: string }
> = {
  "war-room": {
    title: "War Room",
    subtitle: "Floor-decided setups — separate from strategy sessions",
    emptyHint: "Floor-decided signals will show up here.",
  },
  "super-scalping": {
    title: "Super scalping",
    subtitle: "5m ICT — sweep, CHoCH, FVG retest",
    emptyHint: "Setups appear after each 5m close.",
    timeframe: "5m",
  },
  scalping: {
    title: "Scalping",
    subtitle: "15m cloud rejection + CHoCH",
    emptyHint: "Setups appear after each 15m close.",
    timeframe: "15m",
  },
  swing: {
    title: "Swing",
    subtitle: "1h AI-confirmed setups",
    emptyHint: "Setups appear after each 1h close.",
    timeframe: "1h",
  },
};

const BBMA_SESSION = {
  title: "BBMA",
  subtitle: "XAU H1 — live MT5 EA, no AI gate",
  timeframe: "bbma",
  lane: "bbma" as SignalLane,
  emptyHint: "New setups publish on each H1 close from the EA.",
};

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
  strategy = "all",
  page = 1,
  accessToken,
  basePath,
  hideFilter = false,
}: {
  tab: SignalsBrowseTab;
  strategy?: AiSignalStrategy;
  page?: number;
  accessToken?: string;
  basePath: string;
  hideFilter?: boolean;
}) {
  const isAllTab = tab === "all";
  const isAiTab = tab === "ai";
  const isAiWarRoom = isAiTab && strategy === "war-room";
  const isAiStrategy = isAiTab && !isAiWarRoom;
  // "all" strategies within AI Signal has no timeframe filter — only a
  // specific strategy (super-scalping/scalping/swing) narrows it.
  const aiStrategyTimeframe =
    isAiStrategy && strategy !== "all" ? AI_STRATEGY_META[strategy].timeframe : undefined;

  const [allPage, allStats, aiWarRoomPage, aiPage, aiStats] = await Promise.all([
    isAllTab
      ? getSignalsPaginated(page, accessToken, undefined, ALL_PAGE_SIZE)
      : null,
    isAllTab ? getStats(accessToken) : null,
    isAiWarRoom ? getWarRoomSignalsPaginated(page, accessToken) : null,
    isAiStrategy
      ? getSignalsPaginated(page, accessToken, aiStrategyTimeframe, ALL_PAGE_SIZE, "ai")
      : null,
    isAiStrategy ? getStats(accessToken, aiStrategyTimeframe, "ai") : null,
  ]);

  const aiPaginationParams: Record<string, string> =
    strategy === "all" ? { tab: "ai" } : { tab: "ai", strategy };

  return (
    <div className="w-full space-y-8">
      {hideFilter ? (
        <SignalsSessionRail tab={tab} basePath={basePath} />
      ) : (
        <SignalsBrowseFilter tab={tab} basePath={basePath} showLabel={false} compact />
      )}

      {isAiTab ? <AiStrategyRail strategy={strategy} basePath={basePath} /> : null}

      {isAiWarRoom && aiWarRoomPage ? (
        <section className="space-y-5">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold tracking-tight text-ink">War Room</h2>
              <p className="mt-1 text-sm text-slate">
                {AI_STRATEGY_META["war-room"].subtitle}
              </p>
            </div>
            {aiWarRoomPage.total > 0 ? (
              <p className="text-sm text-slate">{aiWarRoomPage.total} total</p>
            ) : null}
          </div>

          {aiWarRoomPage.signals.length > 0 ? (
            <>
              <SignalsGrid signals={aiWarRoomPage.signals} showWarRoomBadge />
              <Pagination
                page={aiWarRoomPage.page}
                totalPages={aiWarRoomPage.totalPages}
                total={aiWarRoomPage.total}
                pageSize={aiWarRoomPage.pageSize}
                basePath={basePath}
                extraParams={aiPaginationParams}
              />
            </>
          ) : (
            <div className="rounded-xl border border-dashed border-line bg-card px-6 py-14 text-center">
              <p className="text-sm font-semibold text-ink">No War Room signals yet</p>
              <p className="mx-auto mt-1.5 max-w-sm text-sm text-slate">
                {AI_STRATEGY_META["war-room"].emptyHint}
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
      ) : isAiStrategy && aiPage && aiStats ? (
        <section className="space-y-5">
          <div>
            <h2 className="text-lg font-semibold tracking-tight text-ink">
              {strategy === "all" ? "AI Signal" : AI_STRATEGY_META[strategy].title}
            </h2>
            <p className="mt-1 text-sm text-slate">
              {strategy === "all"
                ? "Every setup SEA-LION confirmed — across strategies, no floor debate, no raw EA feed."
                : AI_STRATEGY_META[strategy].subtitle}
            </p>
          </div>

          <StatsBar stats={aiStats} />

          {aiPage.signals.length > 0 ? (
            <>
              <SignalsGrid signals={aiPage.signals} />
              <Pagination
                page={aiPage.page}
                totalPages={aiPage.totalPages}
                total={aiPage.total}
                pageSize={aiPage.pageSize}
                basePath={basePath}
                extraParams={aiPaginationParams}
              />
            </>
          ) : (
            <div className="rounded-xl border border-dashed border-line bg-card px-6 py-14 text-center">
              <p className="text-sm font-semibold text-ink">No AI signals yet</p>
              <p className="mx-auto mt-1.5 max-w-sm text-sm text-slate">
                {strategy === "all"
                  ? "New setups will show up here once SEA-LION confirms one."
                  : AI_STRATEGY_META[strategy].emptyHint}
              </p>
            </div>
          )}
        </section>
      ) : (
        <SessionBlock
          accessToken={accessToken}
          title={BBMA_SESSION.title}
          subtitle={BBMA_SESSION.subtitle}
          timeframe={BBMA_SESSION.timeframe}
          lane={BBMA_SESSION.lane}
          emptyHint={BBMA_SESSION.emptyHint}
        />
      )}
    </div>
  );
}
