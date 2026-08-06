import { SignalsGrid } from "@/components/dashboard/SignalsGrid";
import { StatsBar } from "@/components/dashboard/StatsBar";
import { Pagination } from "@/components/shared/Pagination";
import {
  SignalsBrowseFilter,
  type SignalsBrowseTab,
} from "@/components/signals/SignalsBrowseFilter";
import {
  getSignals,
  getStats,
  getWarRoomSignalsPaginated,
  type SignalLane,
} from "@/lib/signals";

export type { SignalsBrowseTab };
export { parseSignalsBrowseTab } from "@/components/signals/SignalsBrowseFilter";

const SESSIONS = [
  {
    id: "super-scalping",
    title: "Super scalping",
    subtitle: "5m ICT — sweep, CHoCH, FVG retest (tight SL/TP)",
    timeframe: "5m",
    lane: "default" as SignalLane,
    emptyHint: "Super-scalp setups fire on each 5m close (cron backup ~10m).",
  },
  {
    id: "scalping",
    title: "Scalping",
    subtitle: "15m chart — cloud rejection + CHoCH setups",
    timeframe: "15m",
    lane: "default" as SignalLane,
    emptyHint: "Scalp setups fire on each 15m close (cron backup ~10m).",
  },
  {
    id: "swing",
    title: "Swing",
    subtitle: "1h chart — AI-confirmed higher-conviction setups",
    timeframe: "1h",
    lane: "default" as SignalLane,
    emptyHint: "Swing setups fire on each 1h close (cron backup ~10m).",
  },
  {
    id: "bbma",
    title: "BBMA",
    subtitle: "XAU H1 taught BBMA — live MT5 EA, no AI gate",
    timeframe: "bbma",
    lane: "bbma" as SignalLane,
    emptyHint: "Pins on the EA chart; new setups publish here on each H1 close.",
  },
] as const;

async function SessionSection({
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
    <section>
      <div className="mb-3 flex items-baseline justify-between">
        <div>
          <h2 className="text-base font-semibold text-ink">{title}</h2>
          <p className="text-xs text-slate">{subtitle}</p>
        </div>
        {signals.length > 0 ? (
          <span className="font-mono text-xs text-slate">
            {signals.length} signal{signals.length === 1 ? "" : "s"}
          </span>
        ) : null}
      </div>

      <StatsBar stats={stats} />

      {signals.length > 0 ? (
        <div className="mt-4">
          <SignalsGrid signals={signals} />
        </div>
      ) : (
        <div className="mt-4 rounded-lg border border-dashed border-line bg-card p-10 text-center">
          <p className="text-sm font-semibold">No {title.toLowerCase()} signals yet</p>
          <p className="mx-auto mt-1 max-w-sm text-xs text-slate">{emptyHint}</p>
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
}: {
  tab: SignalsBrowseTab;
  page?: number;
  accessToken?: string;
  basePath: string;
}) {
  const isWarRoomTab = tab === "war-room";
  const warRoomPage = isWarRoomTab
    ? await getWarRoomSignalsPaginated(page, accessToken)
    : null;

  return (
    <div className="w-full space-y-6">
      <SignalsBrowseFilter tab={tab} basePath={basePath} />

      {isWarRoomTab && warRoomPage ? (
        <section>
          {warRoomPage.signals.length > 0 ? (
            <>
              <SignalsGrid
                signals={warRoomPage.signals}
                showWarRoomBadge
              />
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
            <div className="mt-4 rounded-lg border border-dashed border-line bg-card p-10 text-center">
              <p className="text-sm font-semibold">No War Room signals yet</p>
              <p className="mx-auto mt-1 max-w-sm text-xs text-slate">
                Floor-decided signals will show up here — not strategy-tab trades.
              </p>
            </div>
          )}
        </section>
      ) : tab === "all" ? (
        SESSIONS.map((s) => (
          <SessionSection
            key={s.id}
            title={s.title}
            subtitle={s.subtitle}
            timeframe={s.timeframe}
            lane={s.lane}
            emptyHint={s.emptyHint}
            accessToken={accessToken}
          />
        ))
      ) : (
        <SessionSection
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
