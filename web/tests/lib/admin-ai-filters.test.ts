import { describe, expect, it } from "vitest";

import {
  aiEventsFilterQuery,
  aiResponsesExtraParams,
  aiResponsesHref,
  parseAiEventFilters,
} from "@/lib/admin-ai-filters";

describe("parseAiEventFilters", () => {
  it("parses known filters and uppercases symbol", () => {
    expect(
      parseAiEventFilters({
        symbol: "btcusdt",
        timeframe: "5m",
        kind: "no_setup",
        since: "2026-07-17T05:00:00.000Z",
        until: "2026-07-17T06:00:00.000Z",
      }),
    ).toEqual({
      symbol: "BTCUSDT",
      timeframe: "5m",
      kind: "no_setup",
      since: "2026-07-17T05:00:00.000Z",
      until: "2026-07-17T06:00:00.000Z",
    });
  });

  it("drops unknown timeframe/kind values", () => {
    expect(
      parseAiEventFilters({
        timeframe: "4h",
        kind: "maybe",
        symbol: "  ",
      }),
    ).toEqual({});
  });
});

describe("aiEventsFilterQuery", () => {
  it("builds postgrest filter fragment", () => {
    expect(
      aiEventsFilterQuery({
        symbol: "BTCUSDT",
        timeframe: "5m",
        kind: "reject",
      }),
    ).toBe(
      "&symbol=eq.BTCUSDT&timeframe=eq.5m&kind=eq.reject",
    );
  });

  it("returns empty string when no filters", () => {
    expect(aiEventsFilterQuery({})).toBe("");
  });
});

describe("aiResponsesHref", () => {
  it("omits page=1 and empty filters", () => {
    expect(aiResponsesHref({})).toBe("/admin/ai/responses");
    expect(aiResponsesHref({ kind: "confirm" }, 2)).toBe(
      "/admin/ai/responses?kind=confirm&page=2",
    );
  });

  it("preserves filters in extra params", () => {
    expect(
      aiResponsesExtraParams({ symbol: "ETHUSDT", timeframe: "15m" }),
    ).toEqual({ symbol: "ETHUSDT", timeframe: "15m" });
  });
});
