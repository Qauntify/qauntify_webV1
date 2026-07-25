import { describe, it, expect } from "vitest";
import {
  tradeR, summarize, equityCurve, breakdown, dailyNet, recentTrades,
  toClosedTrade, type ClosedTrade,
} from "@/lib/track-record";

function trade(over: Partial<ClosedTrade> = {}): ClosedTrade {
  return {
    id: "x", symbol: "XAUUSD", timeframe: "5m", direction: "long",
    strategy: "ict_fvg", entry: 100, stopLoss: 98, target: 103,
    status: "tp3_hit", closedAt: "2026-07-01T00:00:00Z", outcomeChartUrl: null,
    ...over,
  };
}

describe("tradeR", () => {
  it("long win = |target-entry| / risk", () => {
    expect(tradeR(trade({ entry: 100, stopLoss: 98, target: 103, status: "tp3_hit" }))).toBeCloseTo(1.5);
  });
  it("short win uses absolute distances", () => {
    expect(tradeR(trade({ direction: "short", entry: 100, stopLoss: 102, target: 97, status: "tp3_hit" }))).toBeCloseTo(1.5);
  });
  it("legacy tp_hit uses its target", () => {
    expect(tradeR(trade({ entry: 100, stopLoss: 98, target: 102, status: "tp_hit" }))).toBeCloseTo(1);
  });
  it("sl_hit is -1R", () => {
    expect(tradeR(trade({ status: "sl_hit" }))).toBe(-1);
  });
  it("risk 0 guards to 0", () => {
    expect(tradeR(trade({ entry: 100, stopLoss: 100, status: "tp3_hit" }))).toBe(0);
  });
});

describe("summarize", () => {
  it("computes rate, netR, avg, streak, updatedAt", () => {
    const ts = [
      trade({ status: "tp3_hit", closedAt: "2026-07-01T00:00:00Z" }),
      trade({ status: "tp3_hit", closedAt: "2026-07-02T00:00:00Z" }),
      trade({ status: "sl_hit", closedAt: "2026-07-03T00:00:00Z" }),
    ];
    const s = summarize(ts);
    expect(s.total).toBe(3);
    expect(s.wins).toBe(2);
    expect(s.losses).toBe(1);
    expect(s.winRate).toBe(67);
    expect(s.netR).toBeCloseTo(2);
    expect(s.bestStreak).toBe(2);
    expect(s.updatedAt).toBe("2026-07-03T00:00:00Z");
  });
  it("empty -> zeros", () => {
    expect(summarize([])).toEqual({
      total: 0, wins: 0, losses: 0, winRate: 0, netR: 0, avgR: 0,
      bestStreak: 0, updatedAt: null,
    });
  });
});

describe("equityCurve", () => {
  it("cumulates in closed order regardless of input order", () => {
    const ts = [
      trade({ status: "sl_hit", closedAt: "2026-07-02T00:00:00Z" }),
      trade({ status: "tp3_hit", closedAt: "2026-07-01T00:00:00Z" }),
    ];
    expect(equityCurve(ts).map((p) => p.r)).toEqual([1.5, 0.5]);
  });
});

describe("breakdown", () => {
  it("groups + sorts by netR desc", () => {
    const ts = [
      trade({ strategy: "ict_fvg", status: "tp3_hit" }),
      trade({ strategy: "sr_zone", status: "sl_hit" }),
    ];
    const rows = breakdown(ts, (t) => t.strategy);
    expect(rows[0].name).toBe("ict_fvg");
    expect(rows[0].winRate).toBe(100);
    expect(rows[1].name).toBe("sr_zone");
    expect(rows[1].netR).toBe(-1);
  });
});

describe("dailyNet", () => {
  it("buckets R by calendar day", () => {
    const ts = [
      trade({ status: "tp3_hit", closedAt: "2026-07-01T05:00:00Z" }),
      trade({ status: "sl_hit", closedAt: "2026-07-01T09:00:00Z" }),
    ];
    expect(dailyNet(ts)).toEqual([{ date: "2026-07-01", net: 0.5 }]);
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
  it("maps a raw row: target, closed_at fallback, strategy, chart url", () => {
    const t = toClosedTrade({
      id: "s1", symbol: "BTCUSD", timeframe: "15m", direction: "short",
      entry: 100, stop_loss: 102, take_profit: 96, take_profit_1: 98,
      take_profit_2: 96, take_profit_3: 94, status: "tp3_hit",
      created_at: "2026-07-01T00:00:00Z", closed_at: null,
      indicators: { strategy: "sr_zone" }, outcome_chart_url: "http://x.png",
    });
    expect(t?.target).toBe(94);
    expect(t?.closedAt).toBe("2026-07-01T00:00:00Z");
    expect(t?.strategy).toBe("sr_zone");
    expect(t?.outcomeChartUrl).toBe("http://x.png");
  });
  it("returns null for a non-terminal status", () => {
    expect(toClosedTrade({
      id: "s", symbol: "X", direction: "long", entry: 1, stop_loss: 1,
      created_at: "2026-07-01T00:00:00Z", status: "open",
    })).toBeNull();
  });
});
