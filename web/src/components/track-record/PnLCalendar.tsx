"use client";

import { useMemo, useState } from "react";
import { buildMonthGrid } from "@/lib/month-grid";
import type { DailyNet } from "@/lib/track-record";

const DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export function PnLCalendar({ daily }: { daily: DailyNet[] }) {
  const netByDate = useMemo(() => {
    const m = new Map<string, number>();
    for (const d of daily) m.set(d.date, d.net);
    return m;
  }, [daily]);

  const latest = daily.length ? daily[daily.length - 1].date : null;

  const [ym, setYm] = useState<{ y: number; m: number }>(() => {
    if (latest) {
      const [y, m] = latest.split("-").map(Number);
      return { y, m: m - 1 };
    }
    const now = new Date();
    return { y: now.getFullYear(), m: now.getMonth() };
  });

  const shift = (delta: number) =>
    setYm(({ y, m }) => {
      const t = y * 12 + m + delta;
      return { y: Math.floor(t / 12), m: ((t % 12) + 12) % 12 };
    });

  const jumpLatest = () => {
    if (!latest) return;
    const [y, m] = latest.split("-").map(Number);
    setYm({ y, m: m - 1 });
  };

  const monthName = new Date(ym.y, ym.m, 1).toLocaleString("default", { month: "long" });
  const cells = useMemo(() => buildMonthGrid(ym.y, ym.m), [ym]);

  return (
    <div>
      <div className="mb-3 flex items-center justify-center gap-3">
        <button onClick={() => shift(-1)} aria-label="Previous month" className="px-2 text-lg leading-none text-slate hover:text-ink">‹</button>
        <span className="min-w-[150px] text-center text-sm font-bold text-ink">{monthName} {ym.y}</span>
        <button onClick={() => shift(1)} aria-label="Next month" className="px-2 text-lg leading-none text-slate hover:text-ink">›</button>
        {latest ? (
          <button onClick={jumpLatest} className="text-[11px] text-slate hover:text-ink">latest</button>
        ) : null}
      </div>
      <div className="overflow-x-auto">
        <div className="min-w-[560px]">
          <div className="mb-1 grid grid-cols-7">
            {DOW.map((d) => (
              <div key={d} className="text-center text-[11px] font-semibold text-slate/70">{d}</div>
            ))}
          </div>
          <div className="grid grid-cols-7 gap-1.5">
            {cells.map((c) => {
              const net = c.inMonth ? netByDate.get(c.dateStr) : undefined;
              let tone = "bg-card border-line";
              if (net !== undefined) {
                tone =
                  net > 0
                    ? "bg-emerald-400/15 border-emerald-400/40"
                    : net < 0
                      ? "bg-rose-400/15 border-rose-400/40"
                      : "bg-slate/15 border-slate/30";
              }
              return (
                <div
                  key={c.dateStr}
                  className={`flex h-16 flex-col rounded-md border p-1.5 ${tone} ${c.inMonth ? "" : "opacity-40"}`}
                >
                  <span className="text-[11px] font-semibold text-slate/80">{c.dayNum}</span>
                  {net !== undefined ? (
                    <span className={`mt-auto text-right text-xs font-bold ${net >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                      {net >= 0 ? "+" : ""}{net}R
                    </span>
                  ) : null}
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
