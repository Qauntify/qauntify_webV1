import { buildContextBlocks, formatSignalsBlock, type SignalSnapshot } from "./context";
import { fetchCalendarBlock } from "./calendar";
import { fetchHeadlinesBlock } from "./news";
import { describeMarketSession } from "./session";
import type { FloorDesk, FloorTone } from "./types";
import type { FloorContextBlocks } from "./prompts";

type Config = { url: string; serviceKey: string };

type SignalRow = {
  symbol?: unknown;
  timeframe?: unknown;
  direction?: unknown;
  status?: unknown;
  entry?: unknown;
  stop_loss?: unknown;
  take_profit?: unknown;
};

function config(): Config | null {
  const url = (process.env.NEXT_PUBLIC_SUPABASE_URL || process.env.SUPABASE_URL)?.trim();
  const serviceKey = process.env.SUPABASE_SERVICE_ROLE_KEY?.trim();
  if (!url || !serviceKey) return null;
  return { url: url.replace(/\/$/, ""), serviceKey };
}

function headers(serviceKey: string): HeadersInit {
  return {
    apikey: serviceKey,
    Authorization: `Bearer ${serviceKey}`,
    "Content-Type": "application/json",
  };
}

function numberValue(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function mapSignalSnapshot(row: SignalRow): SignalSnapshot {
  return {
    symbol: String(row.symbol ?? "unknown"),
    timeframe: String(row.timeframe ?? "unknown"),
    direction: String(row.direction ?? "unknown"),
    status: String(row.status ?? "unknown"),
    entry: numberValue(row.entry),
    stopLoss: numberValue(row.stop_loss),
    takeProfit: numberValue(row.take_profit),
  };
}

export async function insertFloorBrief(input: {
  desk: FloorDesk;
  tone: FloorTone;
  body: string;
  runId: string;
}): Promise<void> {
  const cfg = config();
  if (!cfg) throw new Error("Supabase service-role configuration is unavailable");

  const response = await fetch(`${cfg.url}/rest/v1/floor_briefs`, {
    method: "POST",
    headers: { ...headers(cfg.serviceKey), Prefer: "return=minimal" },
    body: JSON.stringify({
      desk: input.desk,
      tone: input.tone,
      body: input.body,
      run_id: input.runId,
    }),
  });
  if (!response.ok) {
    throw new Error(`Could not insert floor brief (HTTP ${response.status})`);
  }
}

export async function fetchSignalSnapshots(): Promise<SignalSnapshot[]> {
  const cfg = config();
  if (!cfg) return [];

  try {
    const cutoff = new Date(Date.now() - 48 * 60 * 60 * 1000).toISOString();
    const query = new URL(`${cfg.url}/rest/v1/signals`);
    query.searchParams.set(
      "select",
      "symbol,timeframe,direction,status,entry,stop_loss,take_profit",
    );
    query.searchParams.set(
      "or",
      `(status.in.(open,tp1_hit,tp2_hit),created_at.gte."${cutoff}")`,
    );
    query.searchParams.set("order", "created_at.desc");
    query.searchParams.set("limit", "20");

    const response = await fetch(query, {
      headers: headers(cfg.serviceKey),
      cache: "no-store",
    });
    if (!response.ok) return [];

    const rows = (await response.json()) as unknown;
    return Array.isArray(rows)
      ? rows
        .filter((row): row is SignalRow => typeof row === "object" && row !== null)
        .map(mapSignalSnapshot)
      : [];
  } catch {
    return [];
  }
}

export async function loadFloorContext(): Promise<FloorContextBlocks> {
  const [calendarBlock, headlinesBlock, signals] = await Promise.all([
    fetchCalendarBlock(),
    fetchHeadlinesBlock(),
    fetchSignalSnapshots(),
  ]);

  return buildContextBlocks({
    sessionLine: describeMarketSession(),
    calendarBlock,
    headlinesBlock,
    signalsBlock: formatSignalsBlock(signals),
  });
}
