import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StatsBar } from "./StatsBar";

describe("StatsBar", () => {
  it("renders totals and the long/short split", () => {
    render(<StatsBar stats={{ total: 12, avgConfidence: 76, longs: 8, shorts: 4 }} />);
    expect(screen.getByText("12")).toBeDefined();
    expect(screen.getByText("76")).toBeDefined();
    expect(screen.getByText("8L / 4S")).toBeDefined();
  });

  it("shows a dash for average confidence when there are no signals", () => {
    render(<StatsBar stats={{ total: 0, avgConfidence: 0, longs: 0, shorts: 0 }} />);
    expect(screen.getByText("—")).toBeDefined();
  });
});
