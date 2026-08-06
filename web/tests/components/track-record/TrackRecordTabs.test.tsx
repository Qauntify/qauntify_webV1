import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TrackRecordTabs } from "@/components/track-record/TrackRecordTabs";
import type { DailyPnL } from "@/lib/signals";
import type { BreakdownRow, ClosedTrade, DailyNet } from "@/lib/track-record";

const byStrategy: BreakdownRow[] = [{ name: "ict_fvg", winRate: 60, netR: 3, count: 5 }];
const bySymbol: BreakdownRow[] = [{ name: "XAUUSD", winRate: 66, netR: 5, count: 8 }];
const today = new Date();
const todayStr = [
  today.getFullYear(),
  String(today.getMonth() + 1).padStart(2, "0"),
  String(today.getDate()).padStart(2, "0"),
].join("-");
const daily: DailyNet[] = [{ date: todayStr, net: 1.5 }];
const dailyPnL: DailyPnL[] = [{ date: todayStr, wins: 2, losses: 1, net: 1 }];
const recent: ClosedTrade[] = [
  {
    id: "s1", symbol: "XAUUSD", timeframe: "5m", direction: "long",
    strategy: "ict_fvg", entry: 100, stopLoss: 98,
    targets: [102, 104, 106], reached: 3,
    status: "tp3_hit", closedAt: "2026-07-02T00:00:00Z", outcomeChartUrl: null,
  },
];

function setup() {
  return render(
    <TrackRecordTabs
      byStrategy={byStrategy}
      bySymbol={bySymbol}
      daily={daily}
      dailyPnL={dailyPnL}
      recent={recent}
    />,
  );
}

describe("TrackRecordTabs", () => {
  it("defaults to Calendar as the first tab", () => {
    setup();
    expect(screen.queryByText("Overview")).toBeNull();
    expect(screen.getByText("Calendar")).toBeDefined();
    expect(screen.getByText("Breakdown")).toBeDefined();
    expect(screen.getByText("Trades")).toBeDefined();
    expect(screen.getByText(/same calendar as Admin/i)).toBeDefined();
    expect(screen.getByText("2 W")).toBeDefined();
    expect(screen.getByText("1 L")).toBeDefined();
    expect(screen.queryByText(/Recent closed trades/i)).toBeNull();
  });

  it("switches to the Trades panel when the Trades tab is clicked", () => {
    setup();
    fireEvent.click(screen.getByText("Trades"));
    expect(screen.getByText(/Recent closed trades/i)).toBeDefined();
    expect(screen.queryByText(/same calendar as Admin/i)).toBeNull();
  });
});
