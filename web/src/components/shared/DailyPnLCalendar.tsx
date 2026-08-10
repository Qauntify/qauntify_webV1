"use client";

import { useMemo, useState } from "react";

import type { DailyPnL } from "@/lib/signals";

const DAYS_OF_WEEK = ["ច", "អ", "ព", "ព្រ", "សុ", "ស", "អា"];

/** Fixed names — avoid toLocaleString("km-KH") which can SSR as Khmer
 * and hydrate as English when the browser lacks km locale data. */
const MONTHS_KM = [
  "មករា",
  "កុម្ភៈ",
  "មីនា",
  "មេសា",
  "ឧសភា",
  "មិថុនា",
  "កក្កដា",
  "សីហា",
  "កញ្ញា",
  "តុលា",
  "វិច្ឆិកា",
  "ធ្នូ",
] as const;

const DEFAULT_DESCRIPTION =
  "LLM signals ដែលបានបិទតាមថ្ងៃ — រួមទាំងការឈានដល់ TP ពេញលេញ និងការឈ្នះ TP1/TP2 " +
  "(ទោះបីតម្លៃក្រោយមកប៉ះបញ្ឈប់ខាតក៏ដោយ)។ បៃតង = ឈ្នះច្រើនជាងចាញ់។";

type Props = {
  data: DailyPnL[];
  /** Optional blurb above the year tabs. Pass null to hide. */
  description?: string | null;
  /** When false, locks to the current month — no year tabs, no prev/next
   * nav. For compact placements (e.g. the homepage) that don't need
   * browsing, only a snapshot. */
  interactive?: boolean;
  /** Smaller day cells and tighter padding, for placements alongside other
   * content (e.g. the homepage) rather than as the page's main content. */
  compact?: boolean;
};

export function DailyPnLCalendar({
  data,
  description = DEFAULT_DESCRIPTION,
  interactive = true,
  compact = false,
}: Props) {
  const [currentDate, setCurrentDate] = useState(() => new Date());

  const availableYears = useMemo(() => {
    const years = new Set<number>();
    years.add(new Date().getFullYear());
    data.forEach((d) => {
      years.add(new Date(d.date).getFullYear());
    });
    return Array.from(years).sort((a, b) => a - b);
  }, [data]);

  const setYear = (year: number) => {
    setCurrentDate((prev) => {
      const next = new Date(prev);
      next.setFullYear(year);
      return next;
    });
  };

  const prevMonth = () => {
    setCurrentDate((prev) => {
      const next = new Date(prev);
      next.setMonth(next.getMonth() - 1);
      return next;
    });
  };

  const nextMonth = () => {
    setCurrentDate((prev) => {
      const next = new Date(prev);
      next.setMonth(next.getMonth() + 1);
      return next;
    });
  };

  const goToToday = () => {
    setCurrentDate(new Date());
  };

  const year = currentDate.getFullYear();
  const month = currentDate.getMonth();
  const monthName = MONTHS_KM[month];

  const calendarGrid = useMemo(() => {
    const firstDayOfMonth = new Date(year, month, 1);
    const lastDayOfMonth = new Date(year, month + 1, 0);

    let startDayOfWeek = firstDayOfMonth.getDay() - 1;
    if (startDayOfWeek === -1) startDayOfWeek = 6;

    const days: { dateObj: Date; isCurrentMonth: boolean }[] = [];

    const prevMonthLastDate = new Date(year, month, 0).getDate();
    for (let i = startDayOfWeek - 1; i >= 0; i--) {
      const d = new Date(year, month - 1, prevMonthLastDate - i);
      days.push({ dateObj: d, isCurrentMonth: false });
    }

    for (let i = 1; i <= lastDayOfMonth.getDate(); i++) {
      days.push({ dateObj: new Date(year, month, i), isCurrentMonth: true });
    }

    const remainingDays = (7 - (days.length % 7)) % 7;
    for (let i = 1; i <= remainingDays; i++) {
      days.push({ dateObj: new Date(year, month + 1, i), isCurrentMonth: false });
    }

    return days.map((day) => {
      const yyyy = day.dateObj.getFullYear();
      const mm = String(day.dateObj.getMonth() + 1).padStart(2, "0");
      const dd = String(day.dateObj.getDate()).padStart(2, "0");
      const dateStr = `${yyyy}-${mm}-${dd}`;
      const match = data.find((x) => x.date === dateStr);

      return {
        ...day,
        dateStr,
        dayNum: day.dateObj.getDate(),
        net: match?.net ?? 0,
        wins: match?.wins ?? 0,
        losses: match?.losses ?? 0,
        totalTrades: (match?.wins ?? 0) + (match?.losses ?? 0),
      };
    });
  }, [year, month, data]);

  return (
    <div className={`card-surface rounded-xl border border-line ${compact ? "p-4" : "p-6"}`}>
      {description ? (
        <p className="mb-6 text-sm text-slate">{description}</p>
      ) : null}

      {interactive ? (
        <div className="mb-6 flex justify-center">
          <div className="flex overflow-hidden rounded border border-line bg-card">
            {availableYears.map((y) => (
              <button
                key={y}
                type="button"
                onClick={() => setYear(y)}
                className={`px-4 py-2 text-sm font-semibold transition-colors ${
                  year === y
                    ? "bg-slate/10 text-ink"
                    : "text-slate hover:bg-slate/5"
                }`}
              >
                {y}
              </button>
            ))}
          </div>
        </div>
      ) : null}

      <div className="mb-6 flex items-center justify-center gap-4">
        {interactive ? (
          <button
            type="button"
            onClick={prevMonth}
            className="p-1 text-slate transition-colors hover:text-ink"
            aria-label="ខែមុន"
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polyline points="15 18 9 12 15 6"/></svg>
          </button>
        ) : null}

        <div className="flex items-center gap-2">
          <span className="min-w-[120px] text-center text-lg font-bold text-ink">
            {monthName} {year}
          </span>
          {interactive ? (
            <button
              type="button"
              onClick={goToToday}
              className="text-slate transition-colors hover:text-ink"
              title="ទៅថ្ងៃនេះ"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>
            </button>
          ) : null}
        </div>

        {interactive ? (
          <button
            type="button"
            onClick={nextMonth}
            className="p-1 text-slate transition-colors hover:text-ink"
            aria-label="ខែបន្ទាប់"
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polyline points="9 18 15 12 9 6"/></svg>
          </button>
        ) : null}
      </div>

      <div className="custom-scrollbar w-full overflow-x-auto">
        <div className={compact ? "min-w-120" : "min-w-175"}>
          <div className="mb-2 grid grid-cols-7">
            {DAYS_OF_WEEK.map((day) => (
              <div key={day} className="text-center text-sm font-semibold text-ink">
                {day}
              </div>
            ))}
          </div>

          <div className="grid grid-cols-7 gap-2">
            {calendarGrid.map((day, idx) => {
              let bgColor = "bg-card";
              let textColor = "text-ink";

              if (day.totalTrades > 0) {
                if (day.net > 0) {
                  bgColor = "bg-[#67C26D] border-[#67C26D]";
                  textColor = "text-white";
                } else if (day.net < 0) {
                  bgColor = "bg-[#DE4B56] border-[#DE4B56]";
                  textColor = "text-white";
                } else {
                  bgColor = "bg-slate/20 border-slate/30";
                  textColor = "text-ink";
                }
              }

              const opacity = day.isCurrentMonth ? "opacity-100" : "opacity-40";

              return (
                <div
                  key={`${day.dateStr}-${idx}`}
                  className={`flex ${compact ? "h-16 p-1.5" : "h-28 p-2"} flex-col border border-line/70 ${bgColor} ${opacity} transition-colors`}
                >
                  <span className={`${compact ? "text-xs" : "text-sm"} font-semibold ${textColor}`}>
                    {day.dayNum}
                  </span>

                  <div className="mt-1 flex flex-1 flex-col items-center justify-center gap-0.5">
                    {day.totalTrades > 0 ? (
                      <>
                        <span className={`${compact ? "text-xs" : "text-sm"} font-bold ${textColor}`}>
                          {day.wins} TP
                        </span>
                        <span className={`${compact ? "text-xs" : "text-sm"} font-bold ${textColor}`}>
                          {day.losses} SL
                        </span>
                      </>
                    ) : (
                      <>
                        <span className={`${compact ? "text-xs" : "text-sm"} font-semibold text-ink`}>0 TP</span>
                        <span className={`${compact ? "text-xs" : "text-sm"} font-semibold text-ink`}>0 SL</span>
                      </>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
