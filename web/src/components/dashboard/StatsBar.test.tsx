import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StatsBar } from "./StatsBar";

describe("StatsBar", () => {
  it("renders totals, the long/short split, and the win rate", () => {
    render(
      <StatsBar
        stats={{
          total: 12, avgConfidence: 76, longs: 8, shorts: 4,
          tpHits: 3, partialWins: 0, slHits: 1, winRate: 75,
        }}
      />,
    );
    expect(screen.getByText("12")).toBeDefined();
    expect(screen.getByText("76%")).toBeDefined();
    expect(screen.getByText("8L / 4S")).toBeDefined();
    expect(screen.getByText("75%")).toBeDefined();
    expect(screen.getByText("3 full / 0 partial / 1L")).toBeDefined();
  });

  it("shows dashes when there are no signals or closed outcomes", () => {
    render(
      <StatsBar
        stats={{
          total: 0, avgConfidence: 0, longs: 0, shorts: 0,
          tpHits: 0, partialWins: 0, slHits: 0, winRate: null,
        }}
      />,
    );
    expect(screen.getAllByText("—").length).toBe(2);
  });
});
