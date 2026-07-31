import { describe, it, expect } from "vitest";
import {
  tradeR, grossR, scaledR, costR, canonicalSymbol, isWin,
  summarize, equityCurve, breakdown, dailyNet, recentTrades,
  toClosedTrade, type ClosedTrade,
} from "@/lib/track-record";

// A symbol with no COST_BPS entry falls back to the most expensive
// assumption, so tests that are about the R MODEL rather than costs use a
// zero-risk-free construction: entry 100 / stop 98 on XAUUSD costs 0.01R,
// small enough to keep intent readable but still exercised explicitly below.
function trade(over: Partial<ClosedTrade> = {}): ClosedTrade {
  return {
    id: "x", symbol: "XAUUSD", timeframe: "5m", direction: "long",
    strategy: "ict_fvg", entry: 100, stopLoss: 98,
    targets: [102, 104, 106], reached: 3,
    status: "tp3_hit", closedAt: "2026-07-01T00:00:00Z", outcomeChartUrl: null,
    ...over,
  };
}

describe("scaledR", () => {
  it("a full run to the last target is +2R, not +3R", () => {
    expect(scaledR("long", 100, 98, [102, 104, 106], 3, false)).toBeCloseTo(2);
  });
  it("TP1 then reversing into the stop is a net loss", () => {
    // Fixed stop: the booked third is kept, the other two thirds lose 1R each.
    expect(scaledR("long", 100, 98, [102, 104, 106], 1, true)).toBeCloseTo(-1 / 3);
  });
  it("TP2 then reversing keeps two thirds and loses the last", () => {
    expect(scaledR("long", 100, 98, [102, 104, 106], 2, true)).toBeCloseTo(2 / 3);
  });
  it("TP1 then expiring flat keeps the booked third", () => {
    // Expiry is not a stop — nothing is given back.
    expect(scaledR("long", 100, 98, [102, 104, 106], 1, false)).toBeCloseTo(1 / 3);
  });
  it("stopped before any target is the only full -1R", () => {
    expect(scaledR("long", 100, 98, [102, 104, 106], 0, true)).toBe(-1);
  });
  it("untouched expiry is flat", () => {
    expect(scaledR("long", 100, 98, [102, 104, 106], 0, false)).toBe(0);
  });
  it("shorts use absolute distances", () => {
    expect(scaledR("short", 100, 102, [98, 96, 94], 3, false)).toBeCloseTo(2);
  });
  it("a legacy single-target row is one whole slice", () => {
    expect(scaledR("long", 100, 98, [104], 1, false)).toBeCloseTo(2);
  });
  it("risk 0 guards to 0", () => {
    expect(scaledR("long", 100, 100, [102], 1, false)).toBe(0);
  });
});

describe("costR", () => {
  it("is a share of price divided by the stop distance", () => {
    // 20 bps of a 100 price is 0.20; over a 2-point stop that is 0.10R.
    expect(costR("BTCUSD", 100, 98)).toBeCloseTo(0.1);
  });
  it("scales inversely with stop distance", () => {
    expect(costR("BTCUSD", 100, 99)).toBeCloseTo(2 * costR("BTCUSD", 100, 98));
  });
  it("uses the per-symbol rate", () => {
    expect(costR("XAUUSD", 100, 98)).toBeCloseTo(0.01);
    expect(costR("GBPUSD", 100, 98)).toBeCloseTo(0.0075);
  });
  it("unknown symbols take the most expensive assumption, not a free ride", () => {
    expect(costR("DOGEUSD", 100, 98)).toBeCloseTo(0.1);
  });
  it("canonicalises legacy symbols so old rows are priced correctly", () => {
    expect(canonicalSymbol("BTCUSDT")).toBe("BTCUSD");
    expect(canonicalSymbol("PAXGUSDT")).toBe("XAUUSD");
    expect(costR("PAXGUSDT", 100, 98)).toBeCloseTo(costR("XAUUSD", 100, 98));
  });
  it("risk 0 guards to 0", () => {
    expect(costR("BTCUSD", 100, 100)).toBe(0);
  });
});

describe("tradeR", () => {
  it("is gross minus cost", () => {
    const t = trade({ symbol: "BTCUSD" });
    expect(grossR(t)).toBeCloseTo(2);
    expect(tradeR(t)).toBeCloseTo(2 - 0.1);
  });
  it("counts a win by result, not by status", () => {
    // Banking TP2 then reversing ends as "sl_hit" but finished above water.
    expect(isWin(trade({ status: "sl_hit", reached: 2 }))).toBe(true);
    // Banking only TP1 does not: the unbooked two thirds lose their full risk.
    expect(isWin(trade({ status: "sl_hit", reached: 1 }))).toBe(false);
    expect(isWin(trade({ status: "sl_hit", reached: 0 }))).toBe(false);
  });
  it("a win whose targets do not cover costs is a loss", () => {
    // 0.25-point stop on BTCUSD: 20 bps of a 100 price is 0.8R of cost,
    // against +0.67R kept after TP2. Tight stops carry the most cost in R.
    const t = trade({
      symbol: "BTCUSD", entry: 100, stopLoss: 99.75,
      targets: [100.25, 100.5, 100.75], reached: 2, status: "sl_hit",
    });
    expect(grossR(t)).toBeCloseTo(2 / 3);
    expect(tradeR(t)).toBeLessThan(0);
    expect(isWin(t)).toBe(false);
  });
});

describe("summarize", () => {
  it("computes rate, netR, grossR, avg, streak, updatedAt", () => {
    const ts = [
      trade({ symbol: "BTCUSD", status: "tp3_hit", closedAt: "2026-07-01T00:00:00Z" }),
      trade({ symbol: "BTCUSD", status: "tp3_hit", closedAt: "2026-07-02T00:00:00Z" }),
      trade({ symbol: "BTCUSD", status: "sl_hit", reached: 0, closedAt: "2026-07-03T00:00:00Z" }),
    ];
    const s = summarize(ts);
    expect(s.total).toBe(3);
    expect(s.wins).toBe(2);
    expect(s.losses).toBe(1);
    expect(s.winRate).toBe(67);
    // Two +2R winners and one -1R loser = +3R gross, less 0.1R of cost each.
    expect(s.grossR).toBeCloseTo(3);
    expect(s.netR).toBeCloseTo(2.7);
    expect(s.netR).toBeLessThan(s.grossR);
    expect(s.bestStreak).toBe(2);
    expect(s.updatedAt).toBe("2026-07-03T00:00:00Z");
  });
  it("a flat trade is neither a win nor a loss", () => {
    // Zero-cost construction: no targets banked, not stopped.
    const s = summarize([trade({ symbol: "XAUUSD", entry: 100, stopLoss: 0, reached: 0, status: "sl_hit" })]);
    expect(s.total).toBe(1);
    expect(s.winRate).toBe(0);
  });
  it("empty -> zeros", () => {
    expect(summarize([])).toEqual({
      total: 0, wins: 0, losses: 0, breakeven: 0, winRate: 0,
      netR: 0, grossR: 0, avgR: 0, bestStreak: 0, updatedAt: null,
    });
  });
});

describe("equityCurve", () => {
  it("cumulates in closed order regardless of input order", () => {
    const ts = [
      trade({ status: "sl_hit", reached: 0, closedAt: "2026-07-02T00:00:00Z" }),
      trade({ status: "tp3_hit", closedAt: "2026-07-01T00:00:00Z" }),
    ];
    const points = equityCurve(ts).map((p) => p.r);
    expect(points[0]).toBeCloseTo(2, 1);
    expect(points[1]).toBeCloseTo(1, 1);
  });
});

describe("breakdown", () => {
  it("groups + sorts by netR desc", () => {
    const ts = [
      trade({ strategy: "ict_fvg", status: "tp3_hit" }),
      trade({ strategy: "sr_zone", status: "sl_hit", reached: 0 }),
    ];
    const rows = breakdown(ts, (t) => t.strategy);
    expect(rows[0].name).toBe("ict_fvg");
    expect(rows[0].winRate).toBe(100);
    expect(rows[1].name).toBe("sr_zone");
    expect(rows[1].netR).toBeCloseTo(-1, 1);
  });
});

describe("dailyNet", () => {
  it("buckets R by calendar day", () => {
    const ts = [
      trade({ status: "tp3_hit", closedAt: "2026-07-01T05:00:00Z" }),
      trade({ status: "sl_hit", reached: 0, closedAt: "2026-07-01T09:00:00Z" }),
    ];
    const [day] = dailyNet(ts);
    expect(day.date).toBe("2026-07-01");
    expect(day.net).toBeCloseTo(1, 1); // +2R and -1R, less costs
  });
});

describe("recentTrades + toClosedTrade", () => {
  it("recent sorts desc and slices", () => {
    const ts = [
      trade({ id: "a", closedAt: "2026-07-01T00:00:00Z" }),
      trade({ id: "b", closedAt: "2026-07-03T00:00:00Z" }),
    ];
    expect(recentTrades(ts, 1).map((t) => t.id)).toEqual(["b"]);
  });
  it("maps a raw row: ladder, closed_at fallback, strategy, chart url", () => {
    const t = toClosedTrade({
      id: "s1", symbol: "BTCUSD", timeframe: "15m", direction: "short",
      entry: 100, stop_loss: 102, take_profit: 98, take_profit_1: 98,
      take_profit_2: 96, take_profit_3: 94, status: "tp3_hit",
      created_at: "2026-07-01T00:00:00Z", closed_at: null,
      indicators: { strategy: "sr_zone" }, outcome_chart_url: "http://x.png",
    });
    expect(t?.targets).toEqual([98, 96, 94]);
    expect(t?.reached).toBe(3); // terminal win means every target was tagged
    expect(t?.closedAt).toBe("2026-07-01T00:00:00Z");
    expect(t?.strategy).toBe("sr_zone");
    expect(t?.outcomeChartUrl).toBe("http://x.png");
  });
  it("reads partial fills from the tp*_hit_at timestamps", () => {
    const t = toClosedTrade({
      id: "s2", symbol: "BTCUSD", direction: "long",
      entry: 100, stop_loss: 98, take_profit: 102,
      take_profit_2: 104, take_profit_3: 106, status: "sl_hit",
      created_at: "2026-07-01T00:00:00Z",
      tp1_hit_at: "2026-07-01T01:00:00Z",
    });
    expect(t?.reached).toBe(1);
    expect(grossR(t as ClosedTrade)).toBeCloseTo(-1 / 3);
  });
  it("a legacy row with only take_profit is a single-target trade", () => {
    const t = toClosedTrade({
      id: "s3", symbol: "BTCUSD", direction: "long",
      entry: 100, stop_loss: 98, take_profit: 104, status: "tp_hit",
      created_at: "2026-07-01T00:00:00Z",
    });
    expect(t?.targets).toEqual([104]);
    expect(grossR(t as ClosedTrade)).toBeCloseTo(2);
  });
  it("returns null for a non-terminal status", () => {
    expect(toClosedTrade({
      id: "s", symbol: "X", direction: "long", entry: 1, stop_loss: 1,
      created_at: "2026-07-01T00:00:00Z", status: "open",
    })).toBeNull();
  });
});
