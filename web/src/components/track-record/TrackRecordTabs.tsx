"use client";

import { useState } from "react";

import { DailyPnLCalendar } from "@/components/shared/DailyPnLCalendar";
import { Breakdown } from "@/components/track-record/Breakdown";
import { Heatmap } from "@/components/track-record/Heatmap";
import { RecentTrades } from "@/components/track-record/RecentTrades";
import type { DailyPnL } from "@/lib/signals";
import type { BreakdownRow, ClosedTrade, DailyNet } from "@/lib/track-record";

type TabId = "calendar" | "breakdown" | "trades";

const TABS: { id: TabId; label: string }[] = [
  { id: "calendar", label: "Calendar" },
  { id: "breakdown", label: "Breakdown" },
  { id: "trades", label: "Trades" },
];

type Props = {
  byStrategy: BreakdownRow[];
  bySymbol: BreakdownRow[];
  /** R-based daily series for the heatmap strip. */
  daily: DailyNet[];
  /** Same win/loss calendar feed as Admin → Calendar. */
  dailyPnL: DailyPnL[];
  recent: ClosedTrade[];
};

export function TrackRecordTabs({
  byStrategy,
  bySymbol,
  daily,
  dailyPnL,
  recent,
}: Props) {
  const [tab, setTab] = useState<TabId>("calendar");
  return (
    <div>
      <div role="tablist" aria-label="Track record sections" className="mb-4 flex gap-1 overflow-x-auto border-b border-line">
        {TABS.map((t) => (
          <button
            key={t.id}
            role="tab"
            aria-selected={tab === t.id}
            onClick={() => setTab(t.id)}
            className={`-mb-px whitespace-nowrap border-b-2 px-4 py-2 text-sm font-semibold transition-colors ${
              tab === t.id
                ? "border-ink text-ink"
                : "border-transparent text-slate hover:text-ink"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "calendar" ? (
        <div className="space-y-4">
          <div className="rounded-xl border border-line bg-card p-4">
            <div className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-slate/70">Daily net R (last ~13 weeks)</div>
            <Heatmap daily={daily} />
          </div>
          <DailyPnLCalendar
            data={dailyPnL}
            description="Closed signals by day — same calendar as Admin. Full TP hits and TP1/TP2 wins count as wins. Green = more wins than losses."
          />
        </div>
      ) : null}

      {tab === "breakdown" ? (
        <div className="grid gap-4 md:grid-cols-2">
          <Breakdown title="By strategy" rows={byStrategy} />
          <Breakdown title="By symbol" rows={bySymbol} />
        </div>
      ) : null}

      {tab === "trades" ? (
        <div>
          <div className="mb-4 text-[11px] font-semibold uppercase tracking-wider text-slate/70">
            Recent closed trades
          </div>
          <RecentTrades trades={recent} />
        </div>
      ) : null}
    </div>
  );
}
