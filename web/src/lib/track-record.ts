// Pure, browser-side derivation of the public track record from closed-signal
// rows. Every exported function below is pure (no network) so it is unit-tested
// directly; getTrackRecord (added in a later task) does the fetch.

export type ClosedStatus = "tp_hit" | "tp3_hit" | "sl_hit";

export type ClosedTrade = {
  id: string;
  symbol: string;
  timeframe: string;
  direction: "long" | "short";
  strategy: string;
  entry: number;
  stopLoss: number;
  target: number; // realized win-exit price (TP3, or legacy take_profit)
  status: ClosedStatus;
  closedAt: string; // closed_at ?? created_at
  outcomeChartUrl: string | null;
};

export type Summary = {
  total: number;
  wins: number;
  losses: number;
  winRate: number;
  netR: number;
  avgR: number;
  bestStreak: number;
  updatedAt: string | null;
};

export type EquityPoint = { t: string; r: number };
export type BreakdownRow = { name: string; winRate: number; netR: number; count: number };
export type DailyNet = { date: string; net: number };

export type TrackRecord = {
  summary: Summary;
  equity: EquityPoint[];
  byStrategy: BreakdownRow[];
  bySymbol: BreakdownRow[];
  byTimeframe: BreakdownRow[];
  daily: DailyNet[];
  recent: ClosedTrade[];
};

const round1 = (n: number) => Math.round(n * 10) / 10;
const round2 = (n: number) => Math.round(n * 100) / 100;

const WIN = new Set<ClosedStatus>(["tp_hit", "tp3_hit"]);
export function isWin(t: ClosedTrade): boolean {
  return WIN.has(t.status);
}

export function tradeR(t: ClosedTrade): number {
  const risk = Math.abs(t.entry - t.stopLoss);
  if (risk === 0) return 0;
  if (t.status === "sl_hit") return -1;
  return Math.abs(t.target - t.entry) / risk;
}

function byClosedAsc(a: ClosedTrade, b: ClosedTrade): number {
  return a.closedAt.localeCompare(b.closedAt);
}

export function summarize(trades: ClosedTrade[]): Summary {
  const total = trades.length;
  const wins = trades.filter(isWin).length;
  const netR = trades.reduce((s, t) => s + tradeR(t), 0);
  const sorted = [...trades].sort(byClosedAsc);
  let bestStreak = 0;
  let cur = 0;
  for (const t of sorted) {
    if (isWin(t)) {
      cur += 1;
      bestStreak = Math.max(bestStreak, cur);
    } else {
      cur = 0;
    }
  }
  return {
    total,
    wins,
    losses: total - wins,
    winRate: total ? Math.round((wins / total) * 100) : 0,
    netR: round1(netR),
    avgR: total ? round2(netR / total) : 0,
    bestStreak,
    updatedAt: sorted.length ? sorted[sorted.length - 1].closedAt : null,
  };
}

export function equityCurve(trades: ClosedTrade[]): EquityPoint[] {
  let cum = 0;
  return [...trades].sort(byClosedAsc).map((t) => {
    cum += tradeR(t);
    return { t: t.closedAt, r: round2(cum) };
  });
}

export function breakdown(
  trades: ClosedTrade[],
  keyOf: (t: ClosedTrade) => string,
): BreakdownRow[] {
  const groups = new Map<string, ClosedTrade[]>();
  for (const t of trades) {
    const k = keyOf(t) || "—";
    const list = groups.get(k);
    if (list) list.push(t);
    else groups.set(k, [t]);
  }
  return [...groups.entries()]
    .map(([name, ts]) => ({
      name,
      count: ts.length,
      winRate: Math.round((ts.filter(isWin).length / ts.length) * 100),
      netR: round1(ts.reduce((s, t) => s + tradeR(t), 0)),
    }))
    .sort((a, b) => b.netR - a.netR);
}

export function dailyNet(trades: ClosedTrade[]): DailyNet[] {
  const m = new Map<string, number>();
  for (const t of trades) {
    const date = t.closedAt.slice(0, 10);
    m.set(date, (m.get(date) ?? 0) + tradeR(t));
  }
  return [...m.entries()]
    .map(([date, net]) => ({ date, net: round2(net) }))
    .sort((a, b) => a.date.localeCompare(b.date));
}

export function recentTrades(trades: ClosedTrade[], n: number): ClosedTrade[] {
  return [...trades].sort((a, b) => b.closedAt.localeCompare(a.closedAt)).slice(0, n);
}

type RawRow = {
  id: string;
  symbol: string;
  timeframe?: string | null;
  direction: string;
  entry: number;
  stop_loss: number;
  take_profit?: number | null;
  take_profit_1?: number | null;
  take_profit_2?: number | null;
  take_profit_3?: number | null;
  status?: string;
  created_at: string;
  closed_at?: string | null;
  indicators?: Record<string, unknown> | null;
  outcome_chart_url?: string | null;
};

export function toClosedTrade(row: RawRow): ClosedTrade | null {
  const status = row.status;
  if (status !== "tp_hit" && status !== "tp3_hit" && status !== "sl_hit") return null;
  const ind: Record<string, unknown> = row.indicators ?? {};
  const strategy =
    typeof ind.strategy === "string"
      ? (ind.strategy as string)
      : "ema9" in ind
        ? "ema_cross"
        : "—";
  const target =
    status === "tp_hit"
      ? Number(row.take_profit)
      : Number(row.take_profit_3 ?? row.take_profit_1 ?? row.take_profit);
  return {
    id: row.id,
    symbol: row.symbol,
    timeframe: row.timeframe ?? "—",
    direction: row.direction === "short" ? "short" : "long",
    strategy,
    entry: Number(row.entry),
    stopLoss: Number(row.stop_loss),
    target,
    status,
    closedAt: typeof row.closed_at === "string" ? row.closed_at : row.created_at,
    outcomeChartUrl: typeof row.outcome_chart_url === "string" ? row.outcome_chart_url : null,
  };
}

async function fetchClosedRows(accessToken?: string): Promise<RawRow[] | null> {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !anonKey) return null;
  const base = url.replace(/\/$/, "");
  const query =
    "select=id,symbol,timeframe,direction,entry,stop_loss,take_profit," +
    "take_profit_1,take_profit_2,take_profit_3,status,created_at,closed_at," +
    "indicators,outcome_chart_url" +
    "&status=in.(tp_hit,tp3_hit,sl_hit)&order=closed_at.asc.nullslast";
  try {
    const res = await fetch(`${base}/rest/v1/signals?${query}`, {
      headers: { apikey: anonKey, Authorization: `Bearer ${accessToken ?? anonKey}` },
      cache: "no-store",
    });
    if (!res.ok) return null;
    const rows = await res.json();
    return Array.isArray(rows) ? (rows as RawRow[]) : null;
  } catch {
    return null;
  }
}

export async function getTrackRecord(accessToken?: string): Promise<TrackRecord> {
  const rows = await fetchClosedRows(accessToken);
  const trades = (rows ?? [])
    .map(toClosedTrade)
    .filter((t): t is ClosedTrade => t !== null);
  return {
    summary: summarize(trades),
    equity: equityCurve(trades),
    byStrategy: breakdown(trades, (t) => t.strategy),
    bySymbol: breakdown(trades, (t) => t.symbol),
    byTimeframe: breakdown(trades, (t) => t.timeframe),
    daily: dailyNet(trades),
    recent: recentTrades(trades, 20),
  };
}
