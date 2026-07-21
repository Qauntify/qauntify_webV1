/** Kraken public USD market helpers for the web app (no API key). */

export const DEFAULT_MARKET_SYMBOLS = [
  "BTCUSD",
  "ETHUSD",
  "PAXGUSD",
  "GBPUSD",
] as const;

export type MarketInterval = "5m" | "15m" | "1h";

const INTERVAL_MINUTES: Record<MarketInterval, number> = {
  "5m": 5,
  "15m": 15,
  "1h": 60,
};

const KRAKEN_PAIR_BY_SYMBOL: Record<string, string> = {
  BTCUSD: "XBTUSD",
  ETHUSD: "ETHUSD",
  PAXGUSD: "PAXGUSD",
  GBPUSD: "GBPUSD",
  BTCUSDT: "XBTUSD",
  ETHUSDT: "ETHUSD",
  PAXGUSDT: "PAXGUSD",
  GBPUSDT: "GBPUSD",
};

export type MarketCandle = {
  time: number; // unix seconds
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
};

export function canonicalMarketSymbol(symbol: string): string {
  const s = symbol.trim().toUpperCase();
  if (s.endsWith("USDT") && s.length > 4) return `${s.slice(0, -4)}USD`;
  return s;
}

export function krakenPairForSymbol(symbol: string): string {
  const s = symbol.trim().toUpperCase();
  if (KRAKEN_PAIR_BY_SYMBOL[s]) return KRAKEN_PAIR_BY_SYMBOL[s];
  const canon = canonicalMarketSymbol(s);
  if (KRAKEN_PAIR_BY_SYMBOL[canon]) return KRAKEN_PAIR_BY_SYMBOL[canon];
  return canon.startsWith("BTC") ? canon.replace("BTC", "XBT") : canon;
}

export function parseMarketInterval(
  value: string | null | undefined,
): MarketInterval {
  if (value === "5m" || value === "15m" || value === "1h") return value;
  return "1h";
}

export function parseKrakenOhlcPayload(payload: unknown): MarketCandle[] {
  if (!payload || typeof payload !== "object") return [];
  const body = payload as { error?: unknown; result?: Record<string, unknown> };
  const errors = body.error;
  if (Array.isArray(errors) && errors.length > 0) {
    throw new Error(String(errors[0]));
  }
  const result = body.result;
  if (!result || typeof result !== "object") return [];

  let rows: unknown[] | null = null;
  for (const [key, value] of Object.entries(result)) {
    if (key === "last") continue;
    if (Array.isArray(value)) {
      rows = value;
      break;
    }
  }
  if (!rows) return [];

  return rows.flatMap((row) => {
    if (!Array.isArray(row) || row.length < 7) return [];
    return [
      {
        time: Number(row[0]),
        open: Number(row[1]),
        high: Number(row[2]),
        low: Number(row[3]),
        close: Number(row[4]),
        volume: Number(row[6]),
      },
    ];
  });
}

export async function fetchKrakenCandles(
  symbol: string,
  interval: MarketInterval,
  limit = 180,
): Promise<MarketCandle[]> {
  const pair = krakenPairForSymbol(symbol);
  const minutes = INTERVAL_MINUTES[interval];
  const url = new URL("https://api.kraken.com/0/public/OHLC");
  url.searchParams.set("pair", pair);
  url.searchParams.set("interval", String(minutes));

  const response = await fetch(url.toString(), {
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`Kraken HTTP ${response.status}`);
  }
  const candles = parseKrakenOhlcPayload(await response.json());
  // Drop the still-forming last bar so the chart matches engine closed bars.
  const closed =
    candles.length > 1 ? candles.slice(0, -1) : candles;
  if (closed.length > limit) return closed.slice(-limit);
  return closed;
}
