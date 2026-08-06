"use client";

import { useState } from "react";

import { DailyPnLCalendar } from "@/components/shared/DailyPnLCalendar";
import { Breakdown } from "@/components/track-record/Breakdown";
import { RecentTrades } from "@/components/track-record/RecentTrades";
import type { DailyPnL } from "@/lib/signals";
import type { BreakdownRow, ClosedTrade } from "@/lib/track-record";

type TabId = "calendar" | "breakdown" | "trades";

const TABS: { id: TabId; label: string }[] = [
  { id: "calendar", label: "Calendar" },
  { id: "breakdown", label: "Breakdown" },
  { id: "trades", label: "Trades" },
];

type Props = {
  byStrategy: BreakdownRow[];
  bySymbol: BreakdownRow[];
  dailyPnL: DailyPnL[];
  recent: ClosedTrade[];
};

export function TrackRecordTabs({
  byStrategy,
  bySymbol,
  dailyPnL,
  recent,
}: Props) {
  const [tab, setTab] = useState<TabId>("calendar");

  return (
    <div className="space-y-8">
      <nav
        role="tablist"
        aria-label="Track record sections"
        className="flex gap-1 overflow-x-auto border-b border-line [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
      >
        {TABS.map((t) => {
          const active = tab === t.id;
          return (
            <button
              key={t.id}
              type="button"
              role="tab"
              aria-selected={active}
              onClick={() => setTab(t.id)}
              className={`relative shrink-0 whitespace-nowrap px-4 py-3 text-sm font-medium transition-colors ${
                active ? "text-ink" : "text-slate hover:text-ink"
              }`}
            >
              {t.label}
              {active ? (
                <span
                  className="absolute inset-x-2 -bottom-px h-0.5 rounded-full bg-ink"
                  aria-hidden
                />
              ) : null}
            </button>
          );
        })}
      </nav>

      {tab === "calendar" ? (
        <section className="space-y-4">
          <div>
            <h2 className="text-lg font-semibold tracking-tight text-ink">
              Win / loss calendar
            </h2>
            <p className="mt-1 text-sm text-slate">
              Closed signals by day. Full TP and TP1/TP2 wins count as wins.
            </p>
          </div>
          <DailyPnLCalendar data={dailyPnL} description={null} />
        </section>
      ) : null}

      {tab === "breakdown" ? (
        <section className="space-y-5">
          <div>
            <h2 className="text-lg font-semibold tracking-tight text-ink">Breakdown</h2>
            <p className="mt-1 text-sm text-slate">
              Win rate and net R by strategy and symbol
            </p>
          </div>
          <div className="grid gap-5 md:grid-cols-2">
            <Breakdown title="By strategy" rows={byStrategy} />
            <Breakdown title="By symbol" rows={bySymbol} />
          </div>
        </section>
      ) : null}

      {tab === "trades" ? (
        <section className="space-y-5">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold tracking-tight text-ink">
                Recent trades
              </h2>
              <p className="mt-1 text-sm text-slate">Latest closed outcomes</p>
            </div>
            {recent.length > 0 ? (
              <p className="text-sm text-slate">
                {recent.length} trade{recent.length === 1 ? "" : "s"}
              </p>
            ) : null}
          </div>
          <RecentTrades trades={recent} />
        </section>
      ) : null}
    </div>
  );
}
