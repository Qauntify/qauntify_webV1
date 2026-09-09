import { describe, expect, it } from "vitest";

import {
  htfBarsClosedByM1,
  shouldDispatchEngineFromM1Push,
} from "@/lib/bar-close";

describe("htfBarsClosedByM1", () => {
  it("flags 5m close on the last minute of a 5m bucket", () => {
    // 12:04 M1 closes at 12:05 → 5m bar closed
    const open = Date.UTC(2026, 7, 6, 12, 4, 0) / 1000;
    expect(htfBarsClosedByM1(open)).toEqual(["5m"]);
  });

  it("flags 5m+15m+1h on the hour", () => {
    const open = Date.UTC(2026, 7, 6, 12, 59, 0) / 1000;
    expect(htfBarsClosedByM1(open).sort()).toEqual(["15m", "1h", "5m"].sort());
  });

  it("is empty mid-bucket", () => {
    const open = Date.UTC(2026, 7, 6, 12, 2, 0) / 1000;
    expect(htfBarsClosedByM1(open)).toEqual([]);
  });
});

describe("shouldDispatchEngineFromM1Push", () => {
  it("ignores backfill-sized payloads", () => {
    const open = Date.UTC(2026, 7, 6, 12, 59, 0) / 1000;
    const candles = Array.from({ length: 400 }, (_, i) => ({
      open_time: open - i * 60,
    }));
    expect(shouldDispatchEngineFromM1Push(candles)).toEqual([]);
  });

  it("dispatches on a live single-bar HTF close", () => {
    const open = Date.UTC(2026, 7, 6, 12, 14, 0) / 1000;
    expect(shouldDispatchEngineFromM1Push([{ open_time: open }]).sort()).toEqual(
      ["15m", "5m"].sort(),
    );
  });

  it("scans every candle in a batched catch-up push", () => {
    // Mid-bucket bars plus a 15m close — dispatch must see the close even
    // when it is not the newest candle in the array.
    const mid = Date.UTC(2026, 7, 6, 12, 12, 0) / 1000;
    const close15 = Date.UTC(2026, 7, 6, 12, 14, 0) / 1000;
    const newest = Date.UTC(2026, 7, 6, 12, 15, 0) / 1000;
    expect(
      shouldDispatchEngineFromM1Push([
        { open_time: mid },
        { open_time: close15 },
        { open_time: newest },
      ]).sort(),
    ).toEqual(["15m", "5m"].sort());
  });

  it("allows catch-up batches up to 20 bars", () => {
    const open = Date.UTC(2026, 7, 6, 12, 59, 0) / 1000;
    const candles = Array.from({ length: 20 }, (_, i) => ({
      open_time: open - i * 60,
    }));
    expect(shouldDispatchEngineFromM1Push(candles).sort()).toEqual(
      ["15m", "1h", "5m"].sort(),
    );
  });
});
