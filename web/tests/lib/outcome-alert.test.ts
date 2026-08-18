import { describe, expect, it } from "vitest";

import { formatOutcomeAlert } from "@/lib/outcome-alert";
import type { SignalRow } from "@/lib/outcome-rules";

function row(overrides: Partial<SignalRow> = {}): SignalRow {
  return {
    id: "sig-1",
    symbol: "BTCUSDT",
    direction: "long",
    entry: 100.0,
    stop_loss: 95.0,
    take_profit: 110.0,
    status: "open",
    ...overrides,
  };
}

describe("formatOutcomeAlert", () => {
  it("formats a long TP hit with a positive move", () => {
    const text = formatOutcomeAlert(row(), "tp_hit");
    expect(text).toContain("TAKE PROFIT");
    expect(text).toContain("<b>BTCUSDT</b>");
    expect(text).toContain("LONG");
    expect(text).toContain("+10.00 pips");
    expect(text).toContain("Entry  <code>100</code>  →  <code>110</code>");
  });

  it("formats a short SL hit with a negative move", () => {
    const r = row({ direction: "short", stop_loss: 105.0, take_profit: 90.0 });
    const text = formatOutcomeAlert(r, "sl_hit");
    expect(text).toContain("STOP LOSS");
    expect(text).toContain("<b>BTCUSDT</b>");
  });
});
