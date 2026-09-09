/** Detect when a closed MT5 M1 bar completes a higher-timeframe candle.

A closed M1 with `open_time` T covers [T, T+60). The HTF bar that ends at
T+60 has just closed — that is when the signals engine should run.
*/

export const ENGINE_HTF_MINUTES = {
  "5m": 5,
  "15m": 15,
  "1h": 60,
} as const;

export type EngineHtf = keyof typeof ENGINE_HTF_MINUTES;

/** Timeframes whose bar ends exactly when this M1 bar ends. */
export function htfBarsClosedByM1(openTimeSec: number): EngineHtf[] {
  const t = Math.floor(Number(openTimeSec));
  if (!Number.isFinite(t) || t <= 0) return [];
  const barEnd = t + 60;
  const due: EngineHtf[] = [];
  for (const [tf, minutes] of Object.entries(ENGINE_HTF_MINUTES) as [
    EngineHtf,
    number,
  ][]) {
    if (barEnd % (minutes * 60) === 0) due.push(tf);
  }
  return due;
}

/**
 * Whether a candle push should kick the GitHub engine.
 * Live EA catch-up is ≤20 bars; init backfills are hundreds — never trigger those.
 * Scan every candle in the push so a batched catch-up still wakes 5m/15m/1h.
 */
export function shouldDispatchEngineFromM1Push(
  candles: Array<{ open_time: number }>,
  maxLiveBars = 20,
): EngineHtf[] {
  if (!candles.length || candles.length > maxLiveBars) return [];
  const due: EngineHtf[] = [];
  const seen = new Set<EngineHtf>();
  for (const c of candles) {
    for (const tf of htfBarsClosedByM1(Number(c.open_time))) {
      if (!seen.has(tf)) {
        seen.add(tf);
        due.push(tf);
      }
    }
  }
  return due;
}
