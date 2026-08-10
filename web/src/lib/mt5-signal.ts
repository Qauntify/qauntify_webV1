/** Validate + normalize payloads from the MT5 BBMA EA → /api/mt5/signal
 * and chart screenshots → /api/mt5/chart. */

export const MT5_LIVE_SYMBOLS = new Set(["XAUUSD"]);
/** Lane id for the signals page tab — not a candle interval. */
export const MT5_LIVE_TIMEFRAMES = new Set(["bbma"]);
export const MT5_LIVE_STRATEGIES = new Set(["bbma_reentry", "bbma_extreme"]);

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** ~4MB decoded PNG ceiling for EA ChartScreenShot uploads. */
export const MT5_CHART_MAX_BYTES = 4 * 1024 * 1024;

export type Mt5ChartKind = "setup" | "outcome";

export type Mt5ChartPayload = {
  signalId: string;
  kind: Mt5ChartKind;
  png: Buffer;
};

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

/** Candle open_time is epoch ms in Python; MT5 wants unix seconds. */
function timeSec(value: unknown): number | null {
  const n = num(value);
  if (n == null || n <= 0) return null;
  return n > 1e12 ? Math.floor(n / 1000) : Math.floor(n);
}

/** Flatten signal indicators into MT5-friendly annotation numbers. */
export function buildChartAnnotations(
  indicators: Record<string, unknown> | null | undefined,
): Record<string, number> {
  if (!indicators || typeof indicators !== "object") return {};
  const out: Record<string, number> = {};
  const pairs: Array<[string, unknown]> = [
    ["fvg_top", indicators.fvg_top],
    ["fvg_bottom", indicators.fvg_bottom],
    ["fvg_start", indicators.fvg_start_time ?? indicators.fvg_time],
    ["sweep_level", indicators.sweep_level],
    ["sweep_low", indicators.sweep_low],
    ["sweep_high", indicators.sweep_high],
    ["sweep_time", indicators.sweep_time],
    ["choch_level", indicators.choch_level],
    ["choch_time", indicators.choch_time],
    ["cloud_high", indicators.cloud_high],
    ["cloud_low", indicators.cloud_low],
    ["zone_high", indicators.zone_high],
    ["zone_low", indicators.zone_low],
    ["ce_trail", indicators.ce_trail],
    ["retest_time", indicators.retest_time],
  ];
  for (const [key, raw] of pairs) {
    if (key.endsWith("_time") || key === "fvg_start") {
      const t = timeSec(raw);
      if (t != null) out[key] = t;
    } else {
      const v = num(raw);
      if (v != null) out[key] = v;
    }
  }
  return out;
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

function stripDataUrl(b64: string): string {
  const trimmed = b64.trim();
  const comma = trimmed.indexOf(",");
  if (trimmed.startsWith("data:") && comma >= 0) {
    return trimmed.slice(comma + 1);
  }
  return trimmed;
}

function isPng(buf: Buffer): boolean {
  return (
    buf.length >= 8 &&
    buf[0] === 0x89 &&
    buf[1] === 0x50 &&
    buf[2] === 0x4e &&
    buf[3] === 0x47
  );
}

/** Validate MT5 ChartScreenShot upload body for /api/mt5/chart. */
export function parseMt5ChartBody(
  raw: unknown,
): Mt5ChartPayload | { error: string } {
  if (!raw || typeof raw !== "object") return { error: "invalid body" };
  const body = raw as Record<string, unknown>;

  const signalId = String(body.signal_id ?? body.signalId ?? "").trim();
  if (!UUID_RE.test(signalId)) {
    return { error: "signal_id must be a uuid" };
  }

  const kindRaw = String(body.kind ?? "setup").trim().toLowerCase();
  if (kindRaw !== "setup" && kindRaw !== "outcome") {
    return { error: "kind must be setup or outcome" };
  }

  const imageRaw = body.image_base64 ?? body.imageBase64 ?? body.png_base64;
  if (typeof imageRaw !== "string" || !imageRaw.trim()) {
    return { error: "image_base64 required" };
  }

  let png: Buffer;
  try {
    png = Buffer.from(stripDataUrl(imageRaw), "base64");
  } catch {
    return { error: "image_base64 is not valid base64" };
  }
  if (png.length < 32) return { error: "image too small" };
  if (png.length > MT5_CHART_MAX_BYTES) {
    return { error: "image too large" };
  }
  if (!isPng(png)) return { error: "image must be a PNG" };

  return { signalId, kind: kindRaw, png };
}
