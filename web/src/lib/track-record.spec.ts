import { describe, expect, it } from "vitest";

import { toClosedTrade } from "./track-record";

describe("track-record.toClosedTrade mapping", () => {
  it("scores sl_hit as reached=0 even if tp timestamps are present", () => {
    const trade = toClosedTrade({
      id: "sig-1",
      symbol: "BTCUSD",
      timeframe: "15m",
      direction: "long",
      entry: 100,
      stop_loss: 99,
      take_profit: 101, // TP1
      take_profit_1: 101,
      take_profit_2: 102,
      take_profit_3: 103,
      status: "sl_hit",
      created_at: "2026-01-01T00:00:00+00:00",
      closed_at: "2026-01-01T01:00:00+00:00",
      tp1_hit_at: "2026-01-01T00:30:00+00:00",
      tp2_hit_at: null,
      tp3_hit_at: null,
      indicators: null,
      outcome_chart_url: null,
    });

    expect(trade).not.toBeNull();
    if (!trade) return;
    expect(trade.status).toBe("sl_hit");
    expect(trade.reached).toBe(0);
  });

  it("scores tp1_hit as reached=1 when targets exist", () => {
    const trade = toClosedTrade({
      id: "sig-2",
      symbol: "BTCUSD",
      timeframe: "15m",
      direction: "long",
      entry: 100,
      stop_loss: 99,
      take_profit: 101,
      take_profit_1: 101,
      take_profit_2: 102,
      take_profit_3: 103,
      status: "tp1_hit",
      created_at: "2026-01-01T00:00:00+00:00",
      closed_at: "2026-01-01T01:00:00+00:00",
      tp1_hit_at: null, // timestamp drift should not change the public score
      tp2_hit_at: null,
      tp3_hit_at: null,
      indicators: null,
      outcome_chart_url: null,
    });

    expect(trade).not.toBeNull();
    if (!trade) return;
    expect(trade.status).toBe("tp1_hit");
    expect(trade.reached).toBe(1);
  });

  it("caps tp2_hit reached to available targets", () => {
    const trade = toClosedTrade({
      id: "sig-3",
      symbol: "BTCUSD",
      timeframe: "15m",
      direction: "long",
      entry: 100,
      stop_loss: 99,
      take_profit: 101,
      take_profit_1: 101,
      take_profit_2: 102,
      take_profit_3: null, // no TP3 => only 2 targets
      status: "tp2_hit",
      created_at: "2026-01-01T00:00:00+00:00",
      closed_at: "2026-01-01T01:00:00+00:00",
      tp1_hit_at: null,
      tp2_hit_at: null,
      tp3_hit_at: null,
      indicators: null,
      outcome_chart_url: null,
    });

    expect(trade).not.toBeNull();
    if (!trade) return;
    expect(trade.status).toBe("tp2_hit");
    expect(trade.reached).toBe(2);
  });
});

