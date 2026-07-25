import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TrackRecordTabs } from "@/components/track-record/TrackRecordTabs";
import type { BreakdownRow, ClosedTrade, DailyNet, EquityPoint } from "@/lib/track-record";

const equity: EquityPoint[] = [
  { t: "2026-07-01T00:00:00Z", r: 1.5 },
  { t: "2026-07-02T00:00:00Z", r: 0.5 },
];
const byStrategy: BreakdownRow[] = [{ name: "ict_fvg", winRate: 60, netR: 3, count: 5 }];
const bySymbol: BreakdownRow[] = [{ name: "XAUUSD", winRate: 66, netR: 5, count: 8 }];
const daily: DailyNet[] = [{ date: "2026-07-01", net: 1.5 }];
const recent: ClosedTrade[] = [
  {
    id: "s1", symbol: "XAUUSD", timeframe: "5m", direction: "long",
    strategy: "ict_fvg", entry: 100, stopLoss: 98, target: 103,
    status: "tp3_hit", closedAt: "2026-07-02T00:00:00Z", outcomeChartUrl: null,
  },
];

function setup() {
  return render(
    <TrackRecordTabs
      equity={equity}
      byStrategy={byStrategy}
      bySymbol={bySymbol}
      daily={daily}
      recent={recent}
    />,
  );
}

describe("TrackRecordTabs", () => {
  it("shows all four tabs and the Overview panel by default", () => {
    setup();
    expect(screen.getByText("Overview")).toBeDefined();
    expect(screen.getByText("Breakdown")).toBeDefined();
    expect(screen.getByText("Calendar")).toBeDefined();
    expect(screen.getByText("Trades")).toBeDefined();
    expect(screen.getByText(/Cumulative R/i)).toBeDefined();
    expect(screen.queryByText(/Recent closed trades/i)).toBeNull();
  });

  it("switches to the Trades panel when the Trades tab is clicked", () => {
    setup();
    fireEvent.click(screen.getByText("Trades"));
    expect(screen.getByText(/Recent closed trades/i)).toBeDefined();
    expect(screen.queryByText(/Cumulative R/i)).toBeNull();
  });
});
