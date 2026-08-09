"use client";

import { useState } from "react";

import { DailyPnLCalendar } from "@/components/shared/DailyPnLCalendar";
import { Breakdown } from "@/components/track-record/Breakdown";
import { RecentTrades } from "@/components/track-record/RecentTrades";
import type { DailyPnL } from "@/lib/signals";
import type { BreakdownRow, ClosedTrade } from "@/lib/track-record";

type TabId = "calendar" | "breakdown" | "trades";

const TABS: { id: TabId; label: string }[] = [
  { id: "calendar", label: "ប្រតិទិន" },
  { id: "breakdown", label: "ការវិភាគ" },
  { id: "trades", label: "ការជួញដូរ" },
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
        aria-label="ផ្នែកកំណត់ត្រាលទ្ធផល"
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
            <h2 className="text-lg font-semibold tracking-tight text-ink text-center">
              ប្រតិទិន TP/SL
            </h2>
          </div>
          <DailyPnLCalendar data={dailyPnL} description={null} />
        </section>
      ) : null}

      {tab === "breakdown" ? (
        <section className="space-y-5">
          <div>
            <h2 className="text-lg font-semibold tracking-tight text-ink">ការវិភាគ</h2>
            <p className="mt-1 text-sm text-slate">
              អត្រាឈ្នះ និង R សុទ្ធតាមយុទ្ធសាស្ត្រ និងនិមិត្តសញ្ញា
            </p>
          </div>
          <div className="grid gap-5 md:grid-cols-2">
            <Breakdown title="តាមយុទ្ធសាស្ត្រ" rows={byStrategy} />
            <Breakdown title="តាមនិមិត្តសញ្ញា" rows={bySymbol} />
          </div>
        </section>
      ) : null}

      {tab === "trades" ? (
        <section className="space-y-5">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold tracking-tight text-ink">
                ការជួញដូរថ្មីៗ
              </h2>
              <p className="mt-1 text-sm text-slate">លទ្ធផលបិទចុងក្រោយ</p>
            </div>
            {recent.length > 0 ? (
              <p className="text-sm text-slate">
                {recent.length} ការជួញដូរ
              </p>
            ) : null}
          </div>
          <RecentTrades trades={recent} />
        </section>
      ) : null}
    </div>
  );
}
