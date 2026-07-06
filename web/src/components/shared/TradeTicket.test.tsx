import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { Signal } from "@/lib/signals";
import { TradeTicket } from "./TradeTicket";

const SIGNAL: Signal = {
  id: "t1",
  symbol: "BTCUSDT",
  timeframe: "1h",
  direction: "long",
  entry: 108240,
  stopLoss: 106900,
  takeProfit: 110920,
  confidence: 82,
  rationale: "Momentum aligns.",
  indicators: { ema9: 1, ema21: 1, rsi: 55, macdHist: 0.5 },
  newsHeadlines: ["ETF inflows surge"],
  createdAt: new Date().toISOString(),
};

describe("TradeTicket", () => {
  it("renders symbol, direction, prices, confidence, and rationale", () => {
    render(<TradeTicket signal={SIGNAL} />);
    expect(screen.getByText("BTCUSDT")).toBeDefined();
    expect(screen.getByText("▲ Long")).toBeDefined();
    expect(screen.getByText("108,240")).toBeDefined();
    expect(screen.getByText("106,900")).toBeDefined();
    expect(screen.getByText("110,920")).toBeDefined();
    expect(screen.getByText("82")).toBeDefined();
    expect(screen.getByText("“Momentum aligns.”")).toBeDefined();
    expect(screen.getByText("1 headline reviewed")).toBeDefined();
  });

  it("marks sample signals and can hide the rationale", () => {
    render(<TradeTicket signal={SIGNAL} sample showRationale={false} />);
    expect(screen.getByText("example signal")).toBeDefined();
    expect(screen.queryByText("“Momentum aligns.”")).toBeNull();
  });

  it("renders short direction with the short badge", () => {
    render(<TradeTicket signal={{ ...SIGNAL, direction: "short" }} />);
    expect(screen.getByText("▼ Short")).toBeDefined();
  });
});
