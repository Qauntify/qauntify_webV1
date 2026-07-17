import { GOLD_SYMBOL } from "./types";

type Kline = [number, string, string, string, string, ...unknown[]];

function formatTfSummary(label: string, closes: number[]): string {
  if (!closes.length) return `${label}: no data`;
  const last = closes[closes.length - 1];
  const prev = closes[closes.length - 2] ?? last;
  const change = ((last - prev) / prev) * 100;
  const high = Math.max(...closes);
  const low = Math.min(...closes);
  return (
    `${label}: last ${last.toFixed(2)} (${change >= 0 ? "+" : ""}${change.toFixed(2)}%)` +
    ` | range ${low.toFixed(2)}-${high.toFixed(2)}`
  );
}

async function fetchCloses(symbol: string, interval: string, limit = 24): Promise<number[]> {
  const url = new URL("https://api.binance.com/api/v3/klines");
  url.searchParams.set("symbol", symbol);
  url.searchParams.set("interval", interval);
  url.searchParams.set("limit", String(limit));

  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) throw new Error(`Binance HTTP ${response.status}`);

  const rows = (await response.json()) as Kline[];
  return rows
    .slice(0, -1)
    .map((row) => Number.parseFloat(row[4]))
    .filter((value) => Number.isFinite(value));
}

export async function fetchGoldMarketBlock(): Promise<string> {
  try {
    const [m5, m15, h1] = await Promise.all([
      fetchCloses(GOLD_SYMBOL, "5m"),
      fetchCloses(GOLD_SYMBOL, "15m"),
      fetchCloses(GOLD_SYMBOL, "1h"),
    ]);
    return [
      formatTfSummary("5m", m5),
      formatTfSummary("15m", m15),
      formatTfSummary("1h", h1),
    ].join("\n");
  } catch {
    return "Market data unavailable for PAXGUSDT.";
  }
}
