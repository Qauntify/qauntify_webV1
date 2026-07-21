import { describe, expect, it } from "vitest";

import {
  canonicalMarketSymbol,
  isGoldSymbol,
  krakenPairForSymbol,
  parseKrakenOhlcPayload,
  parseMarketInterval,
  parseYahooChartPayload,
} from "@/lib/markets/kraken";

describe("canonicalMarketSymbol", () => {
  it("renames USDT quotes and PAXG to XAUUSD", () => {
    expect(canonicalMarketSymbol("btcusdt")).toBe("BTCUSD");
    expect(canonicalMarketSymbol("ETHUSD")).toBe("ETHUSD");
    expect(canonicalMarketSymbol("PAXGUSD")).toBe("XAUUSD");
    expect(canonicalMarketSymbol("XAUUSD")).toBe("XAUUSD");
  });
});

describe("krakenPairForSymbol", () => {
  it("maps USD and legacy USDT symbols", () => {
    expect(krakenPairForSymbol("BTCUSD")).toBe("XBTUSD");
    expect(krakenPairForSymbol("BTCUSDT")).toBe("XBTUSD");
    expect(krakenPairForSymbol("GBPUSD")).toBe("GBPUSD");
  });
});

describe("isGoldSymbol", () => {
  it("detects gold aliases", () => {
    expect(isGoldSymbol("XAUUSD")).toBe(true);
    expect(isGoldSymbol("PAXGUSDT")).toBe(true);
    expect(isGoldSymbol("ETHUSD")).toBe(false);
  });
});

describe("parseMarketInterval", () => {
  it("defaults unknown values to 1h", () => {
    expect(parseMarketInterval("4h")).toBe("1h");
    expect(parseMarketInterval("15m")).toBe("15m");
  });
});

describe("parseKrakenOhlcPayload", () => {
  it("parses OHLC rows", () => {
    const candles = parseKrakenOhlcPayload({
      error: [],
      result: {
        XXBTZUSD: [
          [1720000000, "100", "102", "99", "101", "100.5", "10", 1],
        ],
        last: 1720000000,
      },
    });
    expect(candles).toEqual([
      {
        time: 1720000000,
        open: 100,
        high: 102,
        low: 99,
        close: 101,
        volume: 10,
      },
    ]);
  });

  it("throws on Kraken error payload", () => {
    expect(() =>
      parseKrakenOhlcPayload({ error: ["EQuery:Unknown asset pair"], result: {} }),
    ).toThrow(/Unknown asset pair/);
  });
});

describe("parseYahooChartPayload", () => {
  it("parses gold futures bars", () => {
    const candles = parseYahooChartPayload({
      chart: {
        result: [
          {
            timestamp: [1720000000],
            indicators: {
              quote: [
                {
                  open: [2300],
                  high: [2310],
                  low: [2290],
                  close: [2305],
                  volume: [12],
                },
              ],
            },
          },
        ],
      },
    });
    expect(candles).toEqual([
      {
        time: 1720000000,
        open: 2300,
        high: 2310,
        low: 2290,
        close: 2305,
        volume: 12,
      },
    ]);
  });
});
