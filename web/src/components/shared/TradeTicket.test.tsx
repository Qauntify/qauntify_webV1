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
  takeProfit2: null,
  takeProfit3: null,
  confidence: 82,
  rationale: "Momentum aligns.",
  indicators: { ema9: 1, ema21: 1, rsi: 55, macdHist: 0.5 },
  newsHeadlines: ["ETF inflows surge"],
  createdAt: new Date().toISOString(),
  closedAt: null,
  status: "open",
};

describe("TradeTicket", () => {
  it("renders symbol, direction, prices, confidence, and rationale", () => {
    render(<TradeTicket signal={SIGNAL} />);
    expect(screen.getByText("BTCUSDT")).toBeDefined();
    expect(screen.getByText("Long")).toBeDefined();
    expect(screen.getByText("108,240")).toBeDefined();
    expect(screen.getByText("106,900")).toBeDefined();
    expect(screen.getByText("110,920")).toBeDefined();
    expect(screen.getByText("82%")).toBeDefined();
    expect(screen.getByText("Momentum aligns.")).toBeDefined();
    expect(screen.getByText("1 headline reviewed")).toBeDefined();
  });

  it("marks sample signals and can hide the rationale", () => {
    render(<TradeTicket signal={SIGNAL} sample showRationale={false} />);
    expect(screen.getByText("example signal")).toBeDefined();
    expect(screen.queryByText("Momentum aligns.")).toBeNull();
  });

  it("shows a status badge only for closed signals", () => {
    const { rerender } = render(<TradeTicket signal={SIGNAL} />);
    expect(screen.queryByText("TP hit")).toBeNull();
    expect(screen.queryByText("SL hit")).toBeNull();
    rerender(<TradeTicket signal={{ ...SIGNAL, status: "tp_hit" }} />);
    expect(screen.getByText("TP hit")).toBeDefined();
    rerender(<TradeTicket signal={{ ...SIGNAL, status: "sl_hit" }} />);
    expect(screen.getByText("SL hit")).toBeDefined();
    rerender(<TradeTicket signal={{ ...SIGNAL, status: "expired" }} />);
    expect(screen.getByText("Expired")).toBeDefined();
  });

  it("renders TP1 TP2 and TP3 when the ladder is filled", () => {
    render(
      <TradeTicket
        signal={{
          ...SIGNAL,
          takeProfit2: 111500,
          takeProfit3: 112500,
        }}
      />,
    );
    expect(screen.getByText("TP1")).toBeDefined();
    expect(screen.getByText("TP2")).toBeDefined();
    expect(screen.getByText("TP3")).toBeDefined();
    expect(screen.getByText("111,500")).toBeDefined();
    expect(screen.getByText("112,500")).toBeDefined();
  });

  it("renders short direction with the short badge", () => {
    render(<TradeTicket signal={{ ...SIGNAL, direction: "short" }} />);
    expect(screen.getByText("Short")).toBeDefined();
  });
});
