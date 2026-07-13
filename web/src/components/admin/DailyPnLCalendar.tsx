"use client";

import type { DailyPnL } from "@/lib/signals";
import { useState, useMemo } from "react";

const DAYS_OF_WEEK = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export function DailyPnLCalendar({ data }: { data: DailyPnL[] }) {
  const [currentDate, setCurrentDate] = useState(() => new Date());

  // Extract available years from data, plus current year
  const availableYears = useMemo(() => {
    const years = new Set<number>();
    years.add(new Date().getFullYear());
    data.forEach((d) => {
      years.add(new Date(d.date).getFullYear());
    });
    return Array.from(years).sort((a, b) => a - b);
  }, [data]);

  // Navigate to specific year while keeping the same month
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
  const month = currentDate.getMonth(); // 0-11
  const monthName = currentDate.toLocaleString("default", { month: "long" });

  // Generate the calendar grid days
  const calendarGrid = useMemo(() => {
    const firstDayOfMonth = new Date(year, month, 1);
    const lastDayOfMonth = new Date(year, month + 1, 0);

    // Day of week: 0 (Sun) to 6 (Sat). We want Monday=0, Sunday=6
    let startDayOfWeek = firstDayOfMonth.getDay() - 1;
    if (startDayOfWeek === -1) startDayOfWeek = 6; // Sunday

    const days = [];
    
    // Previous month padding
    const prevMonthLastDate = new Date(year, month, 0).getDate();
    for (let i = startDayOfWeek - 1; i >= 0; i--) {
      const d = new Date(year, month - 1, prevMonthLastDate - i);
      days.push({ dateObj: d, isCurrentMonth: false });
    }

    // Current month days
    for (let i = 1; i <= lastDayOfMonth.getDate(); i++) {
      const d = new Date(year, month, i);
      days.push({ dateObj: d, isCurrentMonth: true });
    }

    // Next month padding (to complete the last row)
    const remainingDays = (7 - (days.length % 7)) % 7;
    for (let i = 1; i <= remainingDays; i++) {
      const d = new Date(year, month + 1, i);
      days.push({ dateObj: d, isCurrentMonth: false });
    }

    // Map data to days
    return days.map((day) => {
      // Create local ISO string YYYY-MM-DD
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
    <div className="card-surface rounded-xl border border-line p-6">
      <p className="mb-6 text-sm text-slate">
        Closed TP/SL hits by day — green days net wins, red days net losses.
      </p>

      {/* Year Tabs */}
      <div className="flex justify-center mb-6">
        <div className="flex rounded bg-card border border-line overflow-hidden">
          {availableYears.map((y) => (
            <button
              key={y}
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

      {/* Month Navigation */}
      <div className="flex justify-center items-center gap-4 mb-6">
        <button
          onClick={prevMonth}
          className="p-1 text-slate hover:text-ink transition-colors"
          aria-label="Previous Month"
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polyline points="15 18 9 12 15 6"/></svg>
        </button>
        
        <div className="flex items-center gap-2">
          <span className="text-lg font-bold text-ink min-w-[120px] text-center">
            {monthName}
          </span>
          <button
            onClick={goToToday}
            className="text-slate hover:text-ink transition-colors"
            title="Go to Today"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>
          </button>
        </div>

        <button
          onClick={nextMonth}
          className="p-1 text-slate hover:text-ink transition-colors"
          aria-label="Next Month"
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polyline points="9 18 15 12 9 6"/></svg>
        </button>
      </div>

      {/* Calendar Grid */}
      <div className="w-full overflow-x-auto custom-scrollbar">
        <div className="min-w-[700px]">
          {/* Days of Week Header */}
          <div className="grid grid-cols-7 mb-2">
            {DAYS_OF_WEEK.map((day) => (
              <div key={day} className="text-center text-sm font-semibold text-ink">
                {day}
              </div>
            ))}
          </div>

          {/* Grid Cells */}
          <div className="grid grid-cols-7 gap-2">
            {calendarGrid.map((day, idx) => {
              // Determine background color based on net R-multiple (since we don't have $ amounts)
              let bgColor = "bg-card";
              let textColor = "text-ink";
              let subTextColor = "text-slate";
              
              if (day.totalTrades > 0) {
                if (day.net > 0) {
                  bgColor = "bg-[#67C26D] border-[#67C26D]"; // green
                  textColor = "text-white";
                  subTextColor = "text-white/90";
                } else if (day.net < 0) {
                  bgColor = "bg-[#DE4B56] border-[#DE4B56]"; // red
                  textColor = "text-white";
                  subTextColor = "text-white/90";
                } else {
                  bgColor = "bg-slate/20 border-slate/30"; // gray (break even)
                  textColor = "text-ink";
                  subTextColor = "text-ink/80";
                }
              }

              // Dim non-current month days
              const opacity = day.isCurrentMonth ? "opacity-100" : "opacity-40";

              return (
                <div
                  key={`${day.dateStr}-${idx}`}
                  className={`border border-line/70 p-2 h-28 flex flex-col ${bgColor} ${opacity} transition-colors`}
                >
                  <span className={`text-sm font-semibold ${textColor}`}>
                    {day.dayNum}
                  </span>
                  
                  <div className="flex-1 flex flex-col items-center justify-center mt-1 gap-0.5">
                    {day.totalTrades > 0 ? (
                      <>
                        <span className={`text-sm font-bold ${textColor}`}>
                          {day.wins} TP
                        </span>
                        <span className={`text-sm font-bold ${textColor}`}>
                          {day.losses} SL
                        </span>
                      </>
                    ) : (
                      <>
                        <span className="text-sm font-semibold text-ink">0 TP</span>
                        <span className="text-sm font-semibold text-ink">0 SL</span>
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
