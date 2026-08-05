import { describe, expect, it } from "vitest";

import {
  alreadyHit,
  checkTickOutcome,
  stopToPartialWin,
  targets,
  type SignalRow,
} from "@/lib/outcome-rules";

const CLOSED_AT = "2026-07-07T13:00:00.000Z";

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

describe("targets", () => {
  it("collapses cloned TP levels to a single target", () => {
    expect(
      targets({
        take_profit: 110.0, take_profit_1: 110.0,
        take_profit_2: 110.0, take_profit_3: 110.0,
      } as SignalRow),
    ).toEqual([110.0]);
  });

  it("keeps a distinct TP ladder", () => {
    expect(
      targets({
        take_profit: 102.0, take_profit_1: 102.0,
        take_profit_2: 104.0, take_profit_3: 106.0,
      } as SignalRow),
    ).toEqual([102.0, 104.0, 106.0]);
  });
});

describe("stopToPartialWin", () => {
  it("returns null for a pure stop (nothing banked)", () => {
    expect(stopToPartialWin(new Set(), [])).toBeNull();
  });

  it("freezes tp1_hit when only TP1 is banked", () => {
    expect(stopToPartialWin(new Set(["tp1_hit"]), [])).toBe("tp1_hit");
  });

  it("freezes tp2_hit when TP2 is banked", () => {
    expect(stopToPartialWin(new Set(["tp1_hit"]), [["tp2_hit", CLOSED_AT]])).toBe("tp2_hit");
  });

  it("treats a legacy tp_hit event as tp1_hit banked", () => {
    expect(stopToPartialWin(new Set(), [["tp_hit", CLOSED_AT]])).toBe("tp1_hit");
  });
});

describe("checkTickOutcome", () => {
  it("fires tp_hit for a long single-target trade", () => {
    expect(checkTickOutcome(row(), 111.0, CLOSED_AT)).toEqual([["tp_hit", CLOSED_AT]]);
  });

  it("fires sl_hit for a long single-target trade", () => {
    expect(checkTickOutcome(row(), 94.0, CLOSED_AT)).toEqual([["sl_hit", CLOSED_AT]]);
  });

  it("fires tp_hit for a short trade", () => {
    const r = row({ direction: "short", stop_loss: 105.0, take_profit: 90.0 });
    expect(checkTickOutcome(r, 89.0, CLOSED_AT)).toEqual([["tp_hit", CLOSED_AT]]);
  });

  it("fires sl_hit for a short trade", () => {
    const r = row({ direction: "short", stop_loss: 105.0, take_profit: 90.0 });
    expect(checkTickOutcome(r, 106.0, CLOSED_AT)).toEqual([["sl_hit", CLOSED_AT]]);
  });

  it("uses bid for long closes and ask for short closes when both are provided", () => {
    // Long: bid 94 hits SL 95 even though ask is still 96.
    expect(
      checkTickOutcome(row(), { bid: 94.0, ask: 96.0 }, CLOSED_AT),
    ).toEqual([["sl_hit", CLOSED_AT]]);
    // Short: ask 106 hits SL 105 even though bid is still 104.
    const short = row({ direction: "short", stop_loss: 105.0, take_profit: 90.0 });
    expect(
      checkTickOutcome(short, { bid: 104.0, ask: 106.0 }, CLOSED_AT),
    ).toEqual([["sl_hit", CLOSED_AT]]);
  });

  it("returns no events when neither level is reached", () => {
    expect(checkTickOutcome(row(), 105.0, CLOSED_AT)).toEqual([]);
  });

  it("a fast move can cross multiple unhit targets in one tick", () => {
    const r = row({
      take_profit_1: 102.0, take_profit_2: 104.0, take_profit_3: 106.0,
    });
    expect(checkTickOutcome(r, 105.0, CLOSED_AT)).toEqual([
      ["tp1_hit", CLOSED_AT],
      ["tp2_hit", CLOSED_AT],
    ]);
  });

  it("trails the stop to breakeven once a target is banked", () => {
    // TP1 already banked on a previous tick — a pullback to entry (not the
    // original stop) now closes the trade.
    const r = row({ status: "tp1_hit", take_profit_1: 105.0 });
    expect(checkTickOutcome(r, 99.99, CLOSED_AT)).toEqual([["sl_hit", CLOSED_AT]]);
  });

  it("does not trail the stop before any target is banked", () => {
    const r = row();
    // Same price as above, but nothing banked yet — original stop (95) is
    // nowhere close, so this must NOT close the trade.
    expect(checkTickOutcome(r, 99.99, CLOSED_AT)).toEqual([]);
  });

  // No single-tick equivalent of "a candle spanning both levels counts as a
  // stop": that scenario is inherently about a price *range* within one
  // candle. A single tick is one price, so it can never simultaneously
  // satisfy both a stop and a target on opposite sides of entry — the
  // stop-checked-before-targets ordering is still exercised by the plain
  // sl_hit tests above.
});

describe("alreadyHit", () => {
  it("defaults to nothing banked when status is missing", () => {
    expect(alreadyHit({} as SignalRow)).toEqual(new Set());
  });

  it("derives banked levels from status", () => {
    expect(alreadyHit(row({ status: "tp2_hit" }))).toEqual(
      new Set(["tp1_hit", "tp2_hit"]),
    );
  });

  it("derives banked levels from explicit hit timestamps", () => {
    expect(alreadyHit(row({ status: "open", tp1_hit_at: "2026-01-01T00:00:00Z" }))).toEqual(
      new Set(["tp1_hit"]),
    );
  });
});
