/** Public market helpers for the web app (no API key).

Crypto/FX → Kraken. Gold (XAUUSD) → Yahoo Finance GC=F (COMEX gold).
*/

export const DEFAULT_MARKET_SYMBOLS = [
  "BTCUSD",
  "ETHUSD",
  "XAUUSD",
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
  GBPUSD: "GBPUSD",
  BTCUSDT: "XBTUSD",
  ETHUSDT: "ETHUSD",
  GBPUSDT: "GBPUSD",
};

const GOLD_SYMBOLS = new Set(["XAUUSD", "XAUUSDT", "PAXGUSD", "PAXGUSDT"]);

const YAHOO_INTERVAL: Record<MarketInterval, { interval: string; range: string }> = {
  "5m": { interval: "5m", range: "5d" },
  "15m": { interval: "15m", range: "1mo" },
  "1h": { interval: "60m", range: "3mo" },
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
  if (GOLD_SYMBOLS.has(s) || s.startsWith("PAXG") || s.startsWith("XAU")) {
    return "XAUUSD";
  }
  if (s.endsWith("USDT") && s.length > 4) return `${s.slice(0, -4)}USD`;
  return s;
}

export function isGoldSymbol(symbol: string): boolean {
  return canonicalMarketSymbol(symbol) == "XAUUSD";
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

export function parseYahooChartPayload(payload: unknown): MarketCandle[] {
  if (!payload || typeof payload !== "object") return [];
  const chart = (payload as { chart?: { result?: unknown[]; error?: unknown } })
    .chart;
  const results = chart?.result;
  if (!Array.isArray(results) || results.length === 0) {
    throw new Error(
      typeof chart?.error === "object" && chart?.error
        ? JSON.stringify(chart.error)
        : "Yahoo gold chart returned no data",
    );
  }
  const result = results[0] as {
    timestamp?: number[];
    indicators?: { quote?: Array<Record<string, Array<number | null>>> };
  };
  const timestamps = result.timestamp ?? [];
  const quote = result.indicators?.quote?.[0] ?? {};
  const opens = quote.open ?? [];
  const highs = quote.high ?? [];
  const lows = quote.low ?? [];
  const closes = quote.close ?? [];
  const volumes = quote.volume ?? [];

  const candles: MarketCandle[] = [];
  for (let i = 0; i < timestamps.length; i += 1) {
    const o = opens[i];
    const h = highs[i];
    const l = lows[i];
    const c = closes[i];
    if (o == null || h == null || l == null || c == null) continue;
    candles.push({
      time: Number(timestamps[i]),
      open: Number(o),
      high: Number(h),
      low: Number(l),
      close: Number(c),
      volume: Number(volumes[i] ?? 0),
    });
  }
  return candles;
}

async function fetchYahooGoldCandles(
  interval: MarketInterval,
  limit: number,
): Promise<MarketCandle[]> {
  const { interval: yahooInterval, range } = YAHOO_INTERVAL[interval];
  const url = new URL("https://query1.finance.yahoo.com/v8/finance/chart/GC=F");
  url.searchParams.set("interval", yahooInterval);
  url.searchParams.set("range", range);

  const response = await fetch(url.toString(), {
    cache: "no-store",
    headers: { "User-Agent": "Mozilla/5.0" },
  });
  if (!response.ok) {
    throw new Error(`Yahoo gold HTTP ${response.status}`);
  }
  const candles = parseYahooChartPayload(await response.json());
  const closed = candles.length > 1 ? candles.slice(0, -1) : candles;
  if (closed.length > limit) return closed.slice(-limit);
  return closed;
}

async function fetchKrakenOnlyCandles(
  symbol: string,
  interval: MarketInterval,
  limit: number,
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
  const closed = candles.length > 1 ? candles.slice(0, -1) : candles;
  if (closed.length > limit) return closed.slice(-limit);
  return closed;
}

/** @deprecated Prefer fetchMarketCandles — kept for existing imports. */
export async function fetchKrakenCandles(
  symbol: string,
  interval: MarketInterval,
  limit = 180,
): Promise<MarketCandle[]> {
  return fetchMarketCandles(symbol, interval, limit);
}

export async function fetchMarketCandles(
  symbol: string,
  interval: MarketInterval,
  limit = 180,
): Promise<MarketCandle[]> {
  const canon = canonicalMarketSymbol(symbol);
  if (isGoldSymbol(canon)) {
    return fetchYahooGoldCandles(interval, limit);
  }
  return fetchKrakenOnlyCandles(canon, interval, limit);
}
