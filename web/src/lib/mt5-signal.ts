/** Validate + normalize payloads from the MT5 BBMA EA → /api/mt5/signal. */

export const MT5_LIVE_SYMBOLS = new Set(["XAUUSD"]);
export const MT5_LIVE_TIMEFRAMES = new Set(["1h"]);
export const MT5_LIVE_STRATEGIES = new Set(["bbma_reentry", "bbma_extreme"]);

export type Mt5SignalBody = {
  symbol: string;
  timeframe: string;
  direction: "long" | "short";
  entry: number;
  stop_loss: number;
  take_profit: number;
  take_profit_2?: number;
  take_profit_3?: number;
  confidence?: number;
  rationale?: string;
  indicators?: Record<string, unknown>;
  bar_time?: number;
};

export type Mt5SignalPayload = {
  symbol: string;
  timeframe: string;
  direction: "long" | "short";
  entry: number;
  stop_loss: number;
  take_profit: number;
  take_profit_2: number;
  take_profit_3: number;
  confidence: number;
  rationale: string;
  indicators: Record<string, unknown>;
  bar_time: number | null;
};

function num(value: unknown): number | null {
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? n : null;
}

export function parseMt5SignalBody(raw: unknown): Mt5SignalPayload | { error: string } {
  if (!raw || typeof raw !== "object") return { error: "invalid body" };
  const body = raw as Record<string, unknown>;

  const symbol = String(body.symbol ?? "").trim().toUpperCase();
  if (!MT5_LIVE_SYMBOLS.has(symbol)) {
    return { error: `symbol must be one of ${[...MT5_LIVE_SYMBOLS].join(",")}` };
  }

  const timeframe = String(body.timeframe ?? "").trim().toLowerCase();
  if (!MT5_LIVE_TIMEFRAMES.has(timeframe)) {
    return { error: `timeframe must be one of ${[...MT5_LIVE_TIMEFRAMES].join(",")}` };
  }

  const direction = String(body.direction ?? "").trim().toLowerCase();
  if (direction !== "long" && direction !== "short") {
    return { error: "direction must be long or short" };
  }

  const entry = num(body.entry);
  const stop = num(body.stop_loss);
  const tp1 = num(body.take_profit);
  if (entry == null || stop == null || tp1 == null || entry <= 0) {
    return { error: "entry, stop_loss, take_profit required" };
  }

  if (direction === "long") {
    if (!(stop < entry && tp1 > entry)) {
      return { error: "long levels invalid (stop < entry < tp1)" };
    }
  } else if (!(stop > entry && tp1 < entry)) {
    return { error: "short levels invalid (tp1 < entry < stop)" };
  }

  const risk = Math.abs(entry - stop);
  const tp2Raw = num(body.take_profit_2);
  const tp3Raw = num(body.take_profit_3);
  const tp2 =
    tp2Raw != null
      ? tp2Raw
      : direction === "long"
        ? entry + 2 * risk
        : entry - 2 * risk;
  const tp3 =
    tp3Raw != null
      ? tp3Raw
      : direction === "long"
        ? entry + 3 * risk
        : entry - 3 * risk;

  let confidence = num(body.confidence) ?? 75;
  confidence = Math.max(1, Math.min(100, Math.round(confidence)));

  const indicatorsRaw =
    body.indicators && typeof body.indicators === "object"
      ? (body.indicators as Record<string, unknown>)
      : {};
  const strategy = String(indicatorsRaw.strategy ?? "");
  if (!MT5_LIVE_STRATEGIES.has(strategy)) {
    return { error: "indicators.strategy must be bbma_reentry or bbma_extreme" };
  }

  const barTime = num(body.bar_time);
  const rationale =
    typeof body.rationale === "string" && body.rationale.trim()
      ? body.rationale.trim().slice(0, 2000)
      : `Taught BBMA ${strategy} (MT5 EA, live, no AI gate)`;

  return {
    symbol,
    timeframe,
    direction,
    entry,
    stop_loss: stop,
    take_profit: tp1,
    take_profit_2: tp2,
    take_profit_3: tp3,
    confidence,
    rationale,
    indicators: {
      ...indicatorsRaw,
      strategy,
      source: "mt5_ea",
      doctrine: "taught_mtf",
    },
    bar_time: barTime != null && barTime > 0 ? Math.floor(barTime) : null,
  };
}
