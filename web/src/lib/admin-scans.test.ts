import { describe, expect, it } from "vitest";

import {
  aiResponsesHrefForRun,
  aiResponsesWindowForRun,
  countOutcomesByStatus,
  parseEngineOutcomes,
} from "./admin-scans";

describe("parseEngineOutcomes", () => {
  it("maps valid outcome rows", () => {
    const outcomes = parseEngineOutcomes([
      {
        symbol: "BTCUSDT",
        timeframe: "5m",
        status: "NO SIGNAL",
        extra: "no FVG",
      },
      { symbol: "ETHUSDT", status: "SKIPPED", extra: "dedup" },
    ]);
    expect(outcomes).toEqual([
      {
        symbol: "BTCUSDT",
        timeframe: "5m",
        status: "NO SIGNAL",
        extra: "no FVG",
      },
      {
        symbol: "ETHUSDT",
        timeframe: null,
        status: "SKIPPED",
        extra: "dedup",
      },
    ]);
  });

  it("ignores malformed entries", () => {
    expect(parseEngineOutcomes(null)).toEqual([]);
    expect(parseEngineOutcomes([{ status: "ERROR" }])).toEqual([]);
  });
});

describe("countOutcomesByStatus", () => {
  it("counts statuses", () => {
    expect(
      countOutcomesByStatus([
        { symbol: "A", timeframe: "5m", status: "SKIPPED", extra: "" },
        { symbol: "B", timeframe: "5m", status: "NO SIGNAL", extra: "" },
        { symbol: "C", timeframe: "15m", status: "SKIPPED", extra: "" },
      ]),
    ).toEqual({ SKIPPED: 2, "NO SIGNAL": 1 });
  });
});

describe("aiResponsesWindowForRun", () => {
  it("builds a window around finishedAt", () => {
    const finishedAt = "2026-07-17T05:30:00.000Z";
    const { since, until } = aiResponsesWindowForRun(finishedAt);
    expect(Date.parse(until) - Date.parse(finishedAt)).toBe(2 * 60 * 1000);
    expect(Date.parse(finishedAt) - Date.parse(since)).toBe(20 * 60 * 1000);
  });

  it("builds href with optional symbol filter", () => {
    const href = aiResponsesHrefForRun("2026-07-17T05:30:00.000Z", {
      symbol: "BTCUSDT",
      timeframe: "5m",
    });
    expect(href).toContain("/admin/ai/responses?");
    expect(href).toContain("symbol=BTCUSDT");
    expect(href).toContain("timeframe=5m");
    expect(href).toContain("since=");
    expect(href).toContain("until=");
  });
});
