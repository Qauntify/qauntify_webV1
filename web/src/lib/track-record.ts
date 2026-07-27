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
  targets: number[]; // TP1..TP3 present on the row, in order
  reached: number; // how many of them were banked before the trade ended
  status: ClosedStatus;
  closedAt: string; // closed_at ?? created_at
  outcomeChartUrl: string | null;
};

export type Summary = {
  total: number;
  wins: number;
  losses: number;
  breakeven: number;
  winRate: number;
  netR: number;
  grossR: number;
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

// ---------------------------------------------------------------------------
// The R model. Port of signals/r_model.py — keep the two in step.
//
// One third of the position is booked at each of TP1/TP2/TP3, and the stop
// moves to breakeven once TP1 is banked. So a trade that runs all the way to
// the last target returns (1 + 2 + 3) / 3 = +2R, not +3R, and a trade that
// tags TP1 then reverses returns +0.33R, not −1R. This page used to credit the
// full +3R for a winner and a full −1R for any stop, which flattered the
// headline number against the model the engine actually publishes.
// ---------------------------------------------------------------------------

export function scaledR(
  direction: "long" | "short",
  entry: number,
  stopLoss: number,
  targets: number[],
  reached: number,
  stopped: boolean,
): number {
  const risk = Math.abs(entry - stopLoss);
  if (risk === 0 || targets.length === 0) return 0;
  const rOf = (price: number) =>
    direction === "long" ? (price - entry) / risk : (entry - price) / risk;
  const portion = 1 / targets.length;
  let booked = 0;
  for (let k = 0; k < reached; k += 1) booked += portion * rOf(targets[k]);
  if (reached >= targets.length) return booked;
  if (reached === 0 && stopped) return -1;
  return booked; // remainder trails out at breakeven → contributes 0R
}

// Round-trip cost (spread + commission) in basis points of notional.
// MUST match COST_BPS in signals/r_model.py — pinned by a test in both.
const COST_BPS: Record<string, number> = {
  BTCUSD: 20,
  ETHUSD: 20,
  XAUUSD: 2,
  GBPUSD: 1.5,
};
const DEFAULT_COST_BPS = 20;

/** Mirror of signals.market_client.canonical_symbol for legacy stored rows. */
export function canonicalSymbol(symbol: string): string {
  const s = (symbol ?? "").trim().toUpperCase();
  if (s.startsWith("PAXG") || s.startsWith("XAU")) return "XAUUSD";
  if (s.endsWith("USDT") && s.length > 4) return `${s.slice(0, -4)}USD`;
  return s;
}

/**
 * Round-trip cost expressed in R. Cost is a fraction of PRICE while R is a
 * fraction of the stop distance, so the same venue is much more expensive on a
 * tight stop than a wide one.
 */
export function costR(symbol: string, entry: number, stopLoss: number): number {
  const risk = Math.abs(entry - stopLoss);
  if (risk === 0) return 0;
  const bps = COST_BPS[canonicalSymbol(symbol)] ?? DEFAULT_COST_BPS;
  return ((bps / 10_000) * Math.abs(entry)) / risk;
}

/** Realized R before costs. */
export function grossR(t: ClosedTrade): number {
  return scaledR(
    t.direction, t.entry, t.stopLoss, t.targets, t.reached,
    t.status === "sl_hit",
  );
}

/** Realized R after costs — the number quoted publicly. */
export function tradeR(t: ClosedTrade): number {
  const risk = Math.abs(t.entry - t.stopLoss);
  if (risk === 0) return 0;
  return grossR(t) - costR(t.symbol, t.entry, t.stopLoss);
}

/**
 * A win is a trade that finished above water, not one that reached a
 * particular status. Under a scale-out model those differ: banking TP1 and
 * then reversing is a small win, and a "winner" whose targets did not cover
 * its costs is a loss.
 */
export function isWin(t: ClosedTrade): boolean {
  return tradeR(t) > 0;
}

function byClosedAsc(a: ClosedTrade, b: ClosedTrade): number {
  return a.closedAt.localeCompare(b.closedAt);
}

export function summarize(trades: ClosedTrade[]): Summary {
  const total = trades.length;
  const rs = trades.map(tradeR);
  const wins = rs.filter((r) => r > 0).length;
  const losses = rs.filter((r) => r < 0).length;
  const netR = rs.reduce((s, r) => s + r, 0);
  const grossTotal = trades.reduce((s, t) => s + grossR(t), 0);
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
  const decided = wins + losses;
  return {
    total,
    wins,
    losses,
    breakeven: total - decided,
    // Decided outcomes only — a trade that finished exactly flat is neither.
    winRate: decided ? Math.round((wins / decided) * 100) : 0,
    netR: round1(netR),
    grossR: round1(grossTotal),
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
  tp1_hit_at?: string | null;
  tp2_hit_at?: string | null;
  tp3_hit_at?: string | null;
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
  const targets = [
    row.take_profit ?? row.take_profit_1,
    row.take_profit_2,
    row.take_profit_3,
  ]
    .filter((t): t is number => t !== null && t !== undefined)
    .map(Number);
  // How many targets were banked, read from the hit timestamps rather than the
  // final status: a trade that took TP1 and then reversed ends as "sl_hit" but
  // is not a full loss. A terminal win means every target was reached.
  const banked = [row.tp1_hit_at, row.tp2_hit_at, row.tp3_hit_at].filter(Boolean).length;
  const reached =
    status === "tp_hit" || status === "tp3_hit"
      ? targets.length
      : Math.min(banked, targets.length);
  return {
    id: row.id,
    symbol: row.symbol,
    timeframe: row.timeframe ?? "—",
    direction: row.direction === "short" ? "short" : "long",
    strategy,
    entry: Number(row.entry),
    stopLoss: Number(row.stop_loss),
    targets,
    reached,
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
    // The tp*_hit_at timestamps are what make a partial win scoreable.
    "tp1_hit_at,tp2_hit_at,tp3_hit_at," +
    "indicators,outcome_chart_url" +
    "&status=in.(tp_hit,tp3_hit,sl_hit)" +
    // Shadow rows are LLM-rejected setups kept only to measure the gate; they
    // are not recommendations and must never reach the public track record.
    // RLS already blocks them — this is defence in depth.
    "&shadow=is.false" +
    "&order=closed_at.asc.nullslast";
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
