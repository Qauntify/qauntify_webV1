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
});
