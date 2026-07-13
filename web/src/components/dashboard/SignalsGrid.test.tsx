import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { Signal } from "@/lib/signals";
import { SignalsGrid } from "./SignalsGrid";

const SIGNAL: Signal = {
  id: "t1",
  symbol: "BTCUSDT",
  timeframe: "1h",
  direction: "long",
  entry: 108240,
  stopLoss: 106900,
  takeProfit: 110920,
  takeProfit2: null,
  takeProfit3: null,
  confidence: 82,
  rationale: "Momentum aligns with news flow.",
  indicators: { ema9: 1, ema21: 1, rsi: 55, macdHist: 0.5 },
  newsHeadlines: ["ETF inflows surge"],
  createdAt: new Date().toISOString(),
  closedAt: null,
  status: "open",
};

describe("SignalsGrid", () => {
  it("renders signal cards with key prices", () => {
    render(<SignalsGrid signals={[SIGNAL]} />);
    expect(screen.getByText("BTCUSDT")).toBeDefined();
    expect(screen.getByText("Long")).toBeDefined();
    expect(screen.getByText("108,240")).toBeDefined();
    expect(screen.getByText("106,900")).toBeDefined();
    expect(screen.getByText("110,920")).toBeDefined();
    expect(screen.getByText("82%")).toBeDefined();
    expect(screen.queryByText("Momentum aligns with news flow.")).toBeNull();
  });

  it("opens detail modal when a card is clicked", () => {
    render(<SignalsGrid signals={[SIGNAL]} />);
    fireEvent.click(screen.getByRole("button", { name: /btcusdt/i }));
    expect(screen.getByRole("dialog")).toBeDefined();
    expect(screen.getByText("AI rationale")).toBeDefined();
    expect(screen.getByText("Momentum aligns with news flow.")).toBeDefined();
    expect(screen.getByText("ETF inflows surge")).toBeDefined();
  });

  it("closes modal when close button is clicked", () => {
    render(<SignalsGrid signals={[SIGNAL]} />);
    fireEvent.click(screen.getByRole("button", { name: /btcusdt/i }));
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("shows closed status on cards", () => {
    render(<SignalsGrid signals={[{ ...SIGNAL, status: "tp_hit" }]} />);
    expect(screen.getByText("TP hit")).toBeDefined();
  });

  it("grays out the card when the signal hit stop loss", () => {
    render(<SignalsGrid signals={[{ ...SIGNAL, status: "sl_hit" }]} />);
    const card = screen.getByRole("button", { name: /btcusdt/i });
    expect(card.className).toContain("grayscale");
  });

  it("does not gray out open, tp_hit, or expired cards", () => {
    for (const status of ["open", "tp_hit", "expired"] as const) {
      const { unmount } = render(
        <SignalsGrid signals={[{ ...SIGNAL, status }]} />,
      );
      const card = screen.getByRole("button", { name: /btcusdt/i });
      expect(card.className).not.toContain("grayscale");
      unmount();
    }
  });
});
