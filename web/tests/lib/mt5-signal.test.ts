import { describe, expect, it } from "vitest";

import { parseMt5ChartBody, parseMt5SignalBody } from "@/lib/mt5-signal";
import { formatSignalAlert } from "@/lib/outcome-alert";

const valid = {
  symbol: "XAUUSD",
  timeframe: "bbma",
  direction: "long" as const,
  entry: 2650,
  stop_loss: 2640,
  take_profit: 2665,
  take_profit_2: 2680,
  take_profit_3: 2695,
  confidence: 80,
  rationale: "Taught BBMA reentry",
  indicators: { strategy: "bbma_reentry", trigger: "csm", htf_bias: "up" },
};

describe("parseMt5SignalBody", () => {
  it("accepts a valid XAUUSD long", () => {
    const out = parseMt5SignalBody(valid);
    expect("error" in out).toBe(false);
    if ("error" in out) return;
    expect(out.symbol).toBe("XAUUSD");
    expect(out.indicators.source).toBe("mt5_ea");
    expect(out.indicators.doctrine).toBe("taught_mtf");
  });

  it("rejects non-gold symbols", () => {
    const out = parseMt5SignalBody({ ...valid, symbol: "BTCUSD" });
    expect(out).toEqual(expect.objectContaining({ error: expect.any(String) }));
  });

  it("rejects inverted long levels", () => {
    const out = parseMt5SignalBody({
      ...valid,
      stop_loss: 2660,
    });
    expect("error" in out).toBe(true);
  });

  it("rejects unknown strategy", () => {
    const out = parseMt5SignalBody({
      ...valid,
      indicators: { strategy: "ema_cross" },
    });
    expect("error" in out).toBe(true);
  });
});

describe("parseMt5ChartBody", () => {
  // Minimal valid 1x1 PNG
  const png = Buffer.from(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
    "base64",
  );
  const signalId = "a1b2c3d4-e5f6-7890-abcd-ef1234567890";

  it("accepts a setup PNG upload", () => {
    const out = parseMt5ChartBody({
      signal_id: signalId,
      kind: "setup",
      image_base64: png.toString("base64"),
    });
    expect("error" in out).toBe(false);
    if ("error" in out) return;
    expect(out.signalId).toBe(signalId);
    expect(out.kind).toBe("setup");
    expect(out.png.equals(png)).toBe(true);
  });

  it("accepts data-URL and outcome kind", () => {
    const out = parseMt5ChartBody({
      signal_id: signalId,
      kind: "outcome",
      image_base64: `data:image/png;base64,${png.toString("base64")}`,
    });
    expect("error" in out).toBe(false);
    if ("error" in out) return;
    expect(out.kind).toBe("outcome");
  });

  it("rejects non-uuid signal_id", () => {
    const out = parseMt5ChartBody({
      signal_id: "not-a-uuid",
      image_base64: png.toString("base64"),
    });
    expect(out).toEqual(expect.objectContaining({ error: expect.any(String) }));
  });

  it("rejects non-PNG bytes", () => {
    const out = parseMt5ChartBody({
      signal_id: signalId,
      image_base64: Buffer.from("not-a-png").toString("base64"),
    });
    expect(out).toEqual(expect.objectContaining({ error: expect.any(String) }));
  });
});

describe("formatSignalAlert", () => {
  it("includes setup levels and breakeven instruction", () => {
    const text = formatSignalAlert({
      symbol: "XAUUSD",
      timeframe: "1h",
      direction: "long",
      entry: 2650,
      stopLoss: 2640,
      takeProfit: 2665,
      takeProfit2: 2680,
      takeProfit3: 2695,
      confidence: 80,
      rationale: "Taught BBMA",
    });
    expect(text).toContain("LONG SIGNAL");
    expect(text).toContain("XAUUSD");
    expect(text).toContain("move your stop to entry");
    expect(text).toContain("Taught BBMA");
  });
});
