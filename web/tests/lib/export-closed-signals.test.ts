import ExcelJS from "exceljs";
import { describe, expect, it } from "vitest";

import type { Signal } from "@/lib/signals";
import {
  buildClosedSignalsPdf,
  buildClosedSignalsXlsx,
  exportFilename,
  parseExportTab,
  timeframeForTab,
} from "@/lib/export-closed-signals";

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
  chartUrl: null,
  outcomeChartUrl: null,
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

  it("builds a real xlsx buffer", async () => {
    const buf = await buildClosedSignalsXlsx([CLOSED]);
    expect(buf.byteLength).toBeGreaterThan(100);
    // .xlsx is a zip; check the local file header so a truncated or
    // wrong-format buffer cannot pass on size alone.
    expect(Array.from(new Uint8Array(buf).slice(0, 4))).toEqual([0x50, 0x4b, 0x03, 0x04]);
  });

  it("round-trips the exported rows", async () => {
    const buf = await buildClosedSignalsXlsx([CLOSED]);
    const book = new ExcelJS.Workbook();
    await book.xlsx.load(buf);
    const sheet = book.getWorksheet("Closed signals");
    expect(sheet).toBeDefined();
    const header = sheet!.getRow(1).values as unknown[];
    expect(header).toContain("Symbol");
    expect(header).toContain("Rationale");
    expect(sheet!.getRow(2).getCell(1).value).toBe(CLOSED.symbol);
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
