import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RecentTrades } from "@/components/track-record/RecentTrades";
import type { ClosedTrade } from "@/lib/track-record";

const trade: ClosedTrade = {
  id: "s1",
  symbol: "XAUUSD",
  timeframe: "5m",
  direction: "long",
  strategy: "ict_fvg",
  entry: 2400,
  stopLoss: 2390,
  targets: [2410, 2420, 2430],
  reached: 3,
  status: "tp3_hit",
  closedAt: "2026-07-02T00:00:00Z",
  outcomeChartUrl: "https://example.com/chart.png",
};

describe("RecentTrades", () => {
  it("renders closed trades as cards with outcome and R", () => {
    render(<RecentTrades trades={[trade]} />);
    expect(screen.getByText("XAUUSD")).toBeDefined();
    expect(screen.getByText("TP3")).toBeDefined();
    expect(screen.getByText(/\+.*R/)).toBeDefined();
    expect(screen.getByAltText(/outcome chart/i)).toBeDefined();
  });

  it("shows empty state when there are no trades", () => {
    render(<RecentTrades trades={[]} />);
    expect(screen.getByText(/មិនទាន់មានការជួញដូរបិទទេ/i)).toBeDefined();
  });
});
