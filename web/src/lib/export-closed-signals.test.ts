import { describe, expect, it } from "vitest";

import type { Signal } from "@/lib/signals";
import {
  buildClosedSignalsPdf,
  buildClosedSignalsXlsx,
  exportFilename,
  parseExportTab,
  timeframeForTab,
} from "./export-closed-signals";

const CLOSED: Signal = {
  id: "c1",
  symbol: "BTCUSDT",
  timeframe: "1h",
  direction: "long",
  entry: 100,
  stopLoss: 95,
  takeProfit: 110,
  takeProfit2: null,
  takeProfit3: null,
  confidence: 80,
  rationale: "Closed winner.",
  indicators: { ema9: 1, ema21: 1, rsi: 50, macdHist: 0.1 },
  newsHeadlines: [],
  createdAt: "2026-07-06T09:00:00.000Z",
  closedAt: "2026-07-07T10:00:00.000Z",
  status: "tp_hit",
};

describe("export-closed-signals helpers", () => {
  it("maps tabs to timeframes", () => {
    expect(timeframeForTab("all")).toBeUndefined();
    expect(timeframeForTab("super-scalping")).toBe("5m");
    expect(timeframeForTab("scalping")).toBe("15m");
    expect(timeframeForTab("swing")).toBe("1h");
    expect(parseExportTab("super-scalping")).toBe("super-scalping");
    expect(parseExportTab("scalping")).toBe("scalping");
    expect(parseExportTab("nope")).toBe("all");
  });

  it("builds a non-empty xlsx buffer", () => {
    const buf = buildClosedSignalsXlsx([CLOSED]);
    expect(buf.byteLength).toBeGreaterThan(100);
  });

  it("builds a non-empty pdf buffer", () => {
    const buf = buildClosedSignalsPdf([CLOSED], "swing");
    expect(buf.byteLength).toBeGreaterThan(100);
  });

  it("names download files with tab and date", () => {
    expect(exportFilename("xlsx", "all")).toMatch(
      /^qauntify-closed-signals-all-\d{4}-\d{2}-\d{2}\.xlsx$/,
    );
  });
});
