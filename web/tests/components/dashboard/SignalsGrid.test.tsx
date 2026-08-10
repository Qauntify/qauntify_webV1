import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { Signal } from "@/lib/signals";
import { SignalsGrid } from "@/components/dashboard/SignalsGrid";

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
  tp1HitAt: null,
  tp2HitAt: null,
  chartUrl: null,
  outcomeChartUrl: null,
};

describe("SignalsGrid", () => {
  it("renders signal cards with key prices", () => {
    render(<SignalsGrid signals={[SIGNAL]} />);
    expect(screen.getByText("BTCUSDT")).toBeDefined();
    expect(screen.getByText("ទិញ")).toBeDefined();
    expect(screen.getByText("គ្មានគំនូសតាង")).toBeDefined();
    expect(screen.getByText("108,240")).toBeDefined();
    expect(screen.getByText("106,900")).toBeDefined();
    expect(screen.getByText("110,920")).toBeDefined();
    expect(screen.getByText("82%")).toBeDefined();
    expect(screen.queryByText("Momentum aligns with news flow.")).toBeNull();
  });

  it("shows the setup chart image on the card when available", () => {
    render(
      <SignalsGrid
        signals={[{ ...SIGNAL, chartUrl: "https://example.com/setup.png" }]}
      />,
    );
    const img = screen.getByAltText(/btcusdt 1h long chart/i);
    expect(img.getAttribute("src")).toBe("https://example.com/setup.png");
  });

  it("prefers the outcome chart over the setup chart on the card", () => {
    render(
      <SignalsGrid
        signals={[{
          ...SIGNAL,
          chartUrl: "https://example.com/setup.png",
          outcomeChartUrl: "https://example.com/outcome.png",
        }]}
      />,
    );
    const img = screen.getByAltText(/btcusdt 1h long chart/i);
    expect(img.getAttribute("src")).toBe("https://example.com/outcome.png");
  });

  it("opens detail modal when a card is clicked", () => {
    render(<SignalsGrid signals={[SIGNAL]} />);
    fireEvent.click(screen.getByRole("button", { name: /btcusdt/i }));
    expect(screen.getByRole("dialog")).toBeDefined();
    expect(screen.getByText("ហេតុផល AI")).toBeDefined();
    expect(screen.getByText("Momentum aligns with news flow.")).toBeDefined();
    expect(screen.getByText("ETF inflows surge")).toBeDefined();
  });

  it("closes modal when close button is clicked", () => {
    render(<SignalsGrid signals={[SIGNAL]} />);
    fireEvent.click(screen.getByRole("button", { name: /btcusdt/i }));
    fireEvent.click(screen.getByRole("button", { name: "បិទ" }));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("shows closed status on cards", () => {
    render(<SignalsGrid signals={[{ ...SIGNAL, status: "tp_hit" }]} />);
    expect(screen.getByText("TP ប៉ះ")).toBeDefined();
  });

  it("shows TP1 hit when a closed partial win freezes at TP1", () => {
    render(
      <SignalsGrid
        signals={[{
          ...SIGNAL,
          status: "tp1_hit",
          closedAt: "2026-07-01T01:00:00Z",
          tp1HitAt: "2026-07-01T01:00:00Z",
        }]}
      />,
    );
    expect(screen.getByText("TP1 ប៉ះ")).toBeDefined();
    const card = screen.getByRole("button", { name: /btcusdt/i });
    expect(card.className).not.toContain("grayscale");
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
