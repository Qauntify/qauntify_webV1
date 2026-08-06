export type SignalStatus =
  | "open"
  | "tp1_hit"
  | "tp2_hit"
  | "tp3_hit"
  | "tp_hit"
  | "sl_hit"
  | "expired";

export type SignalIndicators = {
  strategy?: string;
  ema9?: number;
  ema21?: number;
  rsi?: number;
  macdHist?: number;
  adx?: number;
  htfTrend?: string;
  structure?: string;
  sweepLevel?: number;
  chochLevel?: number;
  sweepLow?: number;
  sweepHigh?: number;
  atr?: number;
  ceTrail?: number;
  ceDirection?: string;
  lwma200?: number;
  zone?: string;
  side?: string;
  zoneLow?: number;
  zoneHigh?: number;
  touches?: number;
  ceTrend?: string;
  cloudLow?: number;
  cloudHigh?: number;
  ma200?: number;
  trigger?: string;
  bbUpper?: number;
  bbMid?: number;
  bbLower?: number;
  ma5h?: number;
  ma5l?: number;
  ma10h?: number;
  ma10l?: number;
  ema50?: number;
};

export type Signal = {
  id: string;
  symbol: string;
  timeframe: string;
  direction: "long" | "short";
  entry: number;
  stopLoss: number;
  takeProfit: number;
  takeProfit2: number | null;
  takeProfit3: number | null;
  confidence: number;
  rationale: string;
  indicators: SignalIndicators;
  newsHeadlines: string[];
  createdAt: string;
  closedAt: string | null;
  status: SignalStatus;
  tp1HitAt: string | null;
  tp2HitAt: string | null;
  chartUrl: string | null;
  outcomeChartUrl: string | null;
};

export type Stats = {
  total: number;
  avgConfidence: number;
  longs: number;
  shorts: number;
  tpHits: number;
  partialWins: number;
  slHits: number;
  // Percent of decided closed outcomes that banked at least TP1 (full or partial).
  winRate: number | null;
};

type SignalRow = {
  id: string;
  symbol: string;
  timeframe: string;
  direction: string;
  entry: number;
  stop_loss: number;
  take_profit: number;
  take_profit_1?: number | null;
  take_profit_2?: number | null;
  take_profit_3?: number | null;
  confidence: number;
  rationale: string;
  indicators: Record<string, unknown>;
  news_headlines: unknown;
  created_at: string;
  closed_at?: string | null;
  status?: string;
  tp1_hit_at?: string | null;
  tp2_hit_at?: string | null;
  chart_url?: string | null;
  outcome_chart_url?: string | null;
};

function parseStatus(value: string | undefined): SignalStatus {
  if (
    value === "tp_hit" ||
    value === "tp1_hit" ||
    value === "tp2_hit" ||
    value === "tp3_hit" ||
    value === "sl_hit" ||
    value === "expired"
  ) {
    return value;
  }
  return "open";
}

function supabaseConfig(): { url: string; anonKey: string } | null {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !anonKey) return null;
  return { url: url.replace(/\/$/, ""), anonKey };
}

// Shadow rows are LLM-rejected setups stored only to measure the confirmation
// gate. They are not recommendations, so every signals read excludes them.
// RLS already blocks them for anon and member roles — this is defence in depth,
// applied centrally so no caller can forget it.
const EXCLUDE_SHADOW = "&shadow=is.false";
// War Room Floor signals use timeframe=floor — keep them out of strategy tabs.
const EXCLUDE_WAR_ROOM = "&timeframe=neq.floor";
const WAR_ROOM_ONLY = "&timeframe=eq.floor";
// Taught BBMA live lane (EA). New rows use timeframe=bbma; early publishes
// were 1h + indicators.source=mt5_ea — include both so the tab is complete.
const BBMA_LANE =
  "&or=(timeframe.eq.bbma,and(timeframe.eq.1h,indicators->>source.eq.mt5_ea))";
// Swing 1h must not list EA BBMA rows that still carry timeframe=1h.
const EXCLUDE_BBMA_FROM_1H =
  "&or=(indicators->>source.is.null,indicators->>source.neq.mt5_ea)";

export type SignalLane = "default" | "bbma";

function sessionQuery(timeframe?: string, lane: SignalLane = "default"): string {
  if (lane === "bbma") return BBMA_LANE;
  if (timeframe === "1h") {
    return `&timeframe=eq.1h${EXCLUDE_BBMA_FROM_1H}`;
  }
  if (timeframe) return `&timeframe=eq.${timeframe}`;
  return "";
}

async function fetchRows(
  query: string,
  accessToken?: string,
): Promise<SignalRow[] | null> {
  const config = supabaseConfig();
  if (!config) return null;
  try {
    const response = await fetch(
      `${config.url}/rest/v1/signals?${query}${EXCLUDE_SHADOW}${EXCLUDE_WAR_ROOM}`,
      {
        headers: {
          apikey: config.anonKey,
          // A signed-in user's JWT makes RLS grant full history;
          // the anon key alone only sees the 24-hour preview.
          Authorization: `Bearer ${accessToken ?? config.anonKey}`,
        },
        cache: "no-store",
      },
    );
    if (!response.ok) return null;
    const rows = await response.json();
    return Array.isArray(rows) ? rows : null;
  } catch {
    return null;
  }
}

async function callRpc<T>(
  fn: string,
  params: Record<string, unknown>,
  accessToken?: string,
): Promise<T | null> {
  const config = supabaseConfig();
  if (!config) return null;
  try {
    const response = await fetch(`${config.url}/rest/v1/rpc/${fn}`, {
      method: "POST",
      headers: {
        apikey: config.anonKey,
        // A signed-in user's JWT makes RLS grant full history;
        // the anon key alone only sees the 24-hour preview.
        Authorization: `Bearer ${accessToken ?? config.anonKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(params),
      cache: "no-store",
    });
    if (!response.ok) return null;
    return (await response.json()) as T;
  } catch {
    return null;
  }
}

async function fetchRowsPaginated(
  query: string,
  page: number,
  pageSize: number,
  accessToken?: string,
): Promise<{ rows: SignalRow[]; total: number } | null> {
  const config = supabaseConfig();
  if (!config) return null;
  const offset = (page - 1) * pageSize;
  const rangeEnd = offset + pageSize - 1;
  try {
    const response = await fetch(
      `${config.url}/rest/v1/signals?${query}${EXCLUDE_SHADOW}${EXCLUDE_WAR_ROOM}`,
      {
        headers: {
          apikey: config.anonKey,
          Authorization: `Bearer ${accessToken ?? config.anonKey}`,
          Range: `${offset}-${rangeEnd}`,
          Prefer: "count=exact",
        },
        cache: "no-store",
      },
    );
    if (!response.ok) return null;
    const rows = (await response.json()) as SignalRow[];
    const contentRange = response.headers.get("content-range");
    const match = contentRange?.match(/\d+-\d+\/(\d+|\*)/);
    const total = match && match[1] !== "*" ? Number(match[1]) : rows.length;
    return { rows: Array.isArray(rows) ? rows : [], total };
  } catch {
    return null;
  }
}

function num(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function str(value: unknown): string | undefined {
  return typeof value === "string" && value.length > 0 ? value : undefined;
}

function parseIndicators(raw: Record<string, unknown>): SignalIndicators {
  return {
    strategy: str(raw.strategy),
    ema9: num(raw.ema9),
    ema21: num(raw.ema21),
    rsi: num(raw.rsi),
    macdHist: num(raw.macd_hist),
    adx: num(raw.adx),
    htfTrend: str(raw.htf_trend),
    structure: str(raw.structure),
    sweepLevel: num(raw.sweep_level),
    chochLevel: num(raw.choch_level),
    sweepLow: num(raw.sweep_low),
    sweepHigh: num(raw.sweep_high),
    atr: num(raw.atr),
    ceTrail: num(raw.ce_trail),
    ceDirection: str(raw.ce_direction),
    lwma200: num(raw.lwma200),
    zone: str(raw.zone),
    side: str(raw.side),
    zoneLow: num(raw.zone_low),
    zoneHigh: num(raw.zone_high),
    touches: num(raw.touches),
    ceTrend: str(raw.ce_trend),
    cloudLow: num(raw.cloud_low),
    cloudHigh: num(raw.cloud_high),
    ma200: num(raw.ma200),
    trigger: str(raw.trigger),
    bbUpper: num(raw.bb_upper),
    bbMid: num(raw.bb_mid),
    bbLower: num(raw.bb_lower),
    ma5h: num(raw.ma5h),
    ma5l: num(raw.ma5l),
    ma10h: num(raw.ma10h),
    ma10l: num(raw.ma10l),
    ema50: num(raw.ema50),
  };
}

function parseRow(row: SignalRow): Signal | null {
  if (row.direction !== "long" && row.direction !== "short") return null;
  if (!Array.isArray(row.news_headlines)) return null;
  if (typeof row.indicators !== "object" || row.indicators === null) return null;
  const tp1 = row.take_profit_1 ?? row.take_profit;
  return {
    id: row.id,
    symbol: row.symbol,
    timeframe: row.timeframe,
    direction: row.direction,
    entry: row.entry,
    stopLoss: row.stop_loss,
    takeProfit: tp1,
    takeProfit2: typeof row.take_profit_2 === "number" ? row.take_profit_2 : null,
    takeProfit3: typeof row.take_profit_3 === "number" ? row.take_profit_3 : null,
    confidence: row.confidence,
    rationale: row.rationale,
    indicators: parseIndicators(row.indicators),
    newsHeadlines: row.news_headlines as string[],
    createdAt: row.created_at,
    closedAt: typeof row.closed_at === "string" ? row.closed_at : null,
    status: parseStatus(row.status),
    tp1HitAt: typeof row.tp1_hit_at === "string" ? row.tp1_hit_at : null,
    tp2HitAt: typeof row.tp2_hit_at === "string" ? row.tp2_hit_at : null,
    chartUrl: typeof row.chart_url === "string" ? row.chart_url : null,
    outcomeChartUrl: typeof row.outcome_chart_url === "string" ? row.outcome_chart_url : null,
  };
}

export async function getSignals(
  limit = 50,
  accessToken?: string,
  timeframe?: string,
  lane: SignalLane = "default",
): Promise<Signal[]> {
  const filter = sessionQuery(timeframe, lane);
  const rows = await fetchRows(
    `select=*${filter}&order=created_at.desc&limit=${limit}`,
    accessToken,
  );
  if (!rows) return [];
  return rows.map(parseRow).filter((s): s is Signal => s !== null);
}

const ZERO_STATS: Stats = {
  total: 0, avgConfidence: 0, longs: 0, shorts: 0,
  tpHits: 0, partialWins: 0, slHits: 0, winRate: null,
};

function statsFromSignals(signals: Signal[]): Stats {
  const total = signals.length;
  if (total === 0) return ZERO_STATS;
  const longs = signals.filter((s) => s.direction === "long").length;
  const shorts = total - longs;
  const avgConfidence =
    signals.reduce((sum, s) => sum + s.confidence, 0) / total;
  const tpHits = signals.filter(
    (s) => s.status === "tp_hit" || s.status === "tp3_hit",
  ).length;
  const partialWins = signals.filter(
    (s) =>
      (s.status === "tp1_hit" || s.status === "tp2_hit") && s.closedAt != null,
  ).length;
  const slHits = signals.filter((s) => s.status === "sl_hit").length;
  const wins = tpHits + partialWins;
  const closed = wins + slHits;
  return {
    total,
    avgConfidence,
    longs,
    shorts,
    tpHits,
    partialWins,
    slHits,
    winRate: closed > 0 ? Math.round((wins / closed) * 100) : null,
  };
}

type StatsRpcRow = {
  total: number;
  avg_confidence: number;
  longs: number;
  shorts: number;
  tp_hits: number;
  partial_wins?: number;
  sl_hits: number;
};

export async function getStats(
  accessToken?: string,
  timeframe?: string,
  lane: SignalLane = "default",
): Promise<Stats> {
  if (lane === "bbma") {
    // RPC is timeframe-only; BBMA lane mixes bbma + legacy 1h mt5_ea rows.
    return statsFromSignals(await getSignals(500, accessToken, undefined, "bbma"));
  }
  // Aggregated server-side by supabase/schema.sql's get_signal_stats() —
  // counting/averaging in Postgres instead of pulling every matching row
  // into Node. Degrades to zero stats (not a crash) if the RPC 404s, e.g.
  // the migration hasn't been applied to this project yet.
  const row = await callRpc<StatsRpcRow[]>(
    "get_signal_stats",
    { p_timeframe: timeframe ?? null },
    accessToken,
  ).then((rows) => rows?.[0]);
  if (!row) return ZERO_STATS;
  const partialWins = Number(row.partial_wins ?? 0);
  const wins = row.tp_hits + partialWins;
  const closed = wins + row.sl_hits;
  return {
    total: row.total,
    avgConfidence: row.avg_confidence,
    longs: row.longs,
    shorts: row.shorts,
    tpHits: row.tp_hits,
    partialWins,
    slHits: row.sl_hits,
    winRate: closed > 0 ? Math.round((wins / closed) * 100) : null,
  };
}

export const SIGNALS_PAGE_SIZE = 12;

export type SignalsPage = {
  signals: Signal[];
  page: number;
  pageSize: number;
  total: number;
  totalPages: number;
};

export async function getSignalsPaginated(
  page = 1,
  accessToken?: string,
  timeframe?: string,
  pageSize = SIGNALS_PAGE_SIZE,
  lane: SignalLane = "default",
): Promise<SignalsPage> {
  const safePage = Number.isInteger(page) && page > 0 ? page : 1;
  const filter = sessionQuery(timeframe, lane);
  const query = `select=*${filter}&order=created_at.desc`;

  const result = await fetchRowsPaginated(query, safePage, pageSize, accessToken);
  if (!result) {
    return { signals: [], page: 1, pageSize, total: 0, totalPages: 1 };
  }

  const signals = result.rows.map(parseRow).filter((s): s is Signal => s !== null);
  const totalPages = Math.max(1, Math.ceil(result.total / pageSize));
  return {
    signals,
    page: Math.min(safePage, totalPages),
    pageSize,
    total: result.total,
    totalPages,
  };
}

/**
 * War Room Floor signals only (timeframe=floor) — never mixed with strategy tabs.
 */
export async function getWarRoomSignalsPaginated(
  page = 1,
  accessToken?: string,
  pageSize = SIGNALS_PAGE_SIZE,
): Promise<SignalsPage> {
  const safePage = Number.isInteger(page) && page > 0 ? page : 1;
  const query = `select=*${WAR_ROOM_ONLY}&order=created_at.desc`;
  const config = supabaseConfig();
  const empty: SignalsPage = { signals: [], page: 1, pageSize, total: 0, totalPages: 1 };
  if (!config) return empty;

  const offset = (safePage - 1) * pageSize;
  const rangeEnd = offset + pageSize - 1;
  try {
    const response = await fetch(
      `${config.url}/rest/v1/signals?${query}${EXCLUDE_SHADOW}`,
      {
        headers: {
          apikey: config.anonKey,
          Authorization: `Bearer ${accessToken ?? config.anonKey}`,
          Range: `${offset}-${rangeEnd}`,
          Prefer: "count=exact",
        },
        cache: "no-store",
      },
    );
    if (!response.ok) return empty;
    const rows = (await response.json()) as SignalRow[];
    const contentRange = response.headers.get("content-range");
    const match = contentRange?.match(/\d+-\d+\/(\d+|\*)/);
    const total = match && match[1] !== "*" ? Number(match[1]) : rows.length;
    const totalPages = Math.max(1, Math.ceil(total / pageSize) || 1);
    const signals = (Array.isArray(rows) ? rows : [])
      .map(parseRow)
      .filter((s): s is Signal => s !== null);
    return {
      signals,
      page: Math.min(safePage, totalPages),
      pageSize,
      total,
      totalPages,
    };
  } catch {
    return empty;
  }
}

/** Closed TP/SL outcomes only — open and expired are excluded from exports. */
export async function getClosedOutcomeSignals(
  accessToken?: string,
  timeframe?: string,
): Promise<Signal[]> {
  const timeframeFilter = timeframe ? `&timeframe=eq.${timeframe}` : "";
  const rows = await fetchRows(
    `select=*${timeframeFilter}` +
      `&or=(status.in.(tp_hit,tp3_hit,sl_hit),` +
      `and(status.in.(tp1_hit,tp2_hit),closed_at.not.is.null))` +
      `&order=closed_at.desc.nullslast`,
    accessToken,
  );
  if (!rows) return [];
  return rows
    .map(parseRow)
    .filter((s): s is Signal => s !== null)
    .filter((s) =>
      s.status === "tp_hit"
      || s.status === "tp3_hit"
      || s.status === "sl_hit"
      || ((s.status === "tp1_hit" || s.status === "tp2_hit") && s.closedAt != null)
    );
}

export type DailyPnL = {
  date: string; // YYYY-MM-DD
  wins: number;
  losses: number;
  net: number; // wins - losses
};

export async function getDailyPnLStats(
  accessToken?: string,
  days = 365
): Promise<DailyPnL[]> {
  // Fetch all signals in the last N days
  const cutoff = new Date();
  cutoff.setDate(cutoff.getDate() - days);
  
  const query =
    `select=created_at,closed_at,status,tp1_hit_at` +
    `&or=(status.in.(tp_hit,tp3_hit,sl_hit),` +
    `and(status.in.(tp1_hit,tp2_hit),closed_at.not.is.null))` +
    `&created_at=gte.${cutoff.toISOString()}` +
    `&order=created_at.desc`;
  const rows = await fetchRows(query, accessToken);
  
  if (!rows || rows.length === 0) return [];

  const dailyMap = new Map<string, { wins: number; losses: number }>();

  for (const r of rows) {
    const status = parseStatus(r.status);
    const closedPartial =
      (status === "tp1_hit" || status === "tp2_hit")
      && typeof r.closed_at === "string";
    // TP1 banked then later SL still counts as a win (same rule as stats RPC).
    const partialAfterStop =
      status === "sl_hit" && typeof r.tp1_hit_at === "string";
    const isClosedOutcome =
      status === "tp_hit"
      || status === "tp3_hit"
      || status === "sl_hit"
      || closedPartial;
    if (!isClosedOutcome) continue;

    const isWin =
      status === "tp_hit"
      || status === "tp3_hit"
      || closedPartial
      || partialAfterStop;
    
    // Prefer closed day when available — that's when the outcome landed.
    const stamp = typeof r.closed_at === "string" ? r.closed_at : r.created_at;
    const dateStr = new Date(stamp).toISOString().split("T")[0];
    
    if (!dailyMap.has(dateStr)) {
      dailyMap.set(dateStr, { wins: 0, losses: 0 });
    }
    
    const stats = dailyMap.get(dateStr)!;
    if (isWin) stats.wins++;
    else stats.losses++;
  }

  const result: DailyPnL[] = [];
  for (const [date, stats] of dailyMap.entries()) {
    result.push({
      date,
      wins: stats.wins,
      losses: stats.losses,
      net: stats.wins - stats.losses,
    });
  }

  // Sort by date ascending (oldest to newest)
  return result.sort((a, b) => a.date.localeCompare(b.date));
}
