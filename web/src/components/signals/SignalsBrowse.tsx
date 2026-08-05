import Link from "next/link";

import { SignalsGrid } from "@/components/dashboard/SignalsGrid";
import { StatsBar } from "@/components/dashboard/StatsBar";
import { Pagination } from "@/components/shared/Pagination";
import {
  getSignals,
  getStats,
  getWarRoomSignalsPaginated,
} from "@/lib/signals";

const SESSIONS = [
  {
    id: "super-scalping",
    title: "Super scalping",
    subtitle: "5m ICT — sweep, CHoCH, FVG retest (tight SL/TP)",
    timeframe: "5m",
    emptyHint: "Super-scalp setups are checked every ~10 minutes on the 5m chart.",
  },
  {
    id: "scalping",
    title: "Scalping",
    subtitle: "15m chart — cloud rejection + CHoCH setups",
    timeframe: "15m",
    emptyHint: "Scalp setups are checked every ~10 minutes on the 15m chart.",
  },
  {
    id: "swing",
    title: "Swing",
    subtitle: "1h chart — slower, higher-conviction setups",
    timeframe: "1h",
    emptyHint: "Swing setups are checked every ~10 minutes on the 1h chart.",
  },
] as const;

export type SignalsBrowseTab =
  | "all"
  | "war-room"
  | "super-scalping"
  | "scalping"
  | "swing";

export function parseSignalsBrowseTab(tab: string | undefined): SignalsBrowseTab {
  if (tab === "war-room") return "war-room";
  if (tab === "swing") return "swing";
  if (tab === "scalping") return "scalping";
  if (tab === "super-scalping") return "super-scalping";
  return "all";
}

async function SessionSection({
  title,
  subtitle,
  timeframe,
  emptyHint,
  accessToken,
}: {
  title: string;
  subtitle: string;
  timeframe: string;
  emptyHint: string;
  accessToken: string | undefined;
}) {
  const [signals, stats] = await Promise.all([
    getSignals(30, accessToken, timeframe),
    getStats(accessToken, timeframe),
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

  const tabHref = (t: string) =>
    t === "all" ? basePath : `${basePath}?tab=${t}`;

  return (
    <div className="w-full space-y-6">
      <nav className="relative flex gap-2 overflow-x-auto border-b border-line pb-4">
        {(
          [
            ["all", "All"],
            ["war-room", "War Room"],
            ["super-scalping", "Super scalp (5m)"],
            ["scalping", "Scalping (15m)"],
            ["swing", "Swing (1h)"],
          ] as const
        ).map(([id, label]) => (
          <Link
            key={id}
            href={tabHref(id)}
            className={`rounded-full px-4 py-2 text-sm font-medium transition-all duration-200 ${
              tab === id
                ? "bg-ink text-paper shadow-md"
                : "text-slate hover:bg-card hover:text-ink"
            }`}
          >
            {label}
          </Link>
        ))}
      </nav>

      {isWarRoomTab && warRoomPage ? (
        <section>
          <div className="mb-5 rounded-lg border border-accent/20 bg-accent-soft/40 px-4 py-3">
            <p className="text-xs font-semibold uppercase tracking-wide text-accent">
              War Room
            </p>
            <p className="mt-1 text-sm text-slate">
              Showing {warRoomPage.total} signal
              {warRoomPage.total === 1 ? "" : "s"} with a War Room debate.
            </p>
          </div>

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
                Signals with an AI War Room debate will show up here.
              </p>
            </div>
          )}
        </section>
      ) : tab === "all" ? (
        SESSIONS.map((s) => (
          <SessionSection
            key={s.timeframe}
            title={s.title}
            subtitle={s.subtitle}
            timeframe={s.timeframe}
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
          emptyHint={SESSIONS.find((s) => s.id === tab)!.emptyHint}
        />
      )}
    </div>
  );
}
