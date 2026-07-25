"use client";

import { useState } from "react";

import { Breakdown } from "@/components/track-record/Breakdown";
import { EquityCurve } from "@/components/track-record/EquityCurve";
import { Heatmap } from "@/components/track-record/Heatmap";
import { PnLCalendar } from "@/components/track-record/PnLCalendar";
import { RecentTrades } from "@/components/track-record/RecentTrades";
import type { BreakdownRow, ClosedTrade, DailyNet, EquityPoint } from "@/lib/track-record";

type TabId = "overview" | "breakdown" | "calendar" | "trades";

const TABS: { id: TabId; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "breakdown", label: "Breakdown" },
  { id: "calendar", label: "Calendar" },
  { id: "trades", label: "Trades" },
];

type Props = {
  equity: EquityPoint[];
  byStrategy: BreakdownRow[];
  bySymbol: BreakdownRow[];
  daily: DailyNet[];
  recent: ClosedTrade[];
};

export function TrackRecordTabs({ equity, byStrategy, bySymbol, daily, recent }: Props) {
  const [tab, setTab] = useState<TabId>("overview");
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
                ? "border-accent text-accent"
                : "border-transparent text-slate hover:text-ink"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "overview" ? (
        <div className="rounded-xl border border-line bg-card p-4">
          <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate/70">Cumulative R (all closed trades)</div>
          <EquityCurve points={equity} />
        </div>
      ) : null}

      {tab === "breakdown" ? (
        <div className="grid gap-4 md:grid-cols-2">
          <Breakdown title="By strategy" rows={byStrategy} />
          <Breakdown title="By symbol" rows={bySymbol} />
        </div>
      ) : null}

      {tab === "calendar" ? (
        <div className="space-y-4">
          <div className="rounded-xl border border-line bg-card p-4">
            <div className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-slate/70">Daily net (last ~13 weeks)</div>
            <Heatmap daily={daily} />
          </div>
          <div className="rounded-xl border border-line bg-card p-4">
            <div className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-slate/70">Monthly P&amp;L (net R per day)</div>
            <PnLCalendar daily={daily} />
          </div>
        </div>
      ) : null}

      {tab === "trades" ? (
        <div className="rounded-xl border border-line bg-card p-4">
          <div className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-slate/70">Recent closed trades</div>
          <RecentTrades trades={recent} />
        </div>
      ) : null}
    </div>
  );
}
