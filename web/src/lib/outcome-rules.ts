/**
 * Ported from signals/outcome_tracker.py — the SL/TP decision rules only.
 * Chart generation is NOT ported (see docs/plan); this only decides status.
 *
 * checkTickOutcome is a narrowed port of check_outcome_events for a single
 * live price instead of a candle array — safe because a live tick's time is
 * always >= the signal's created_at, so the candle-history-window filtering
 * check_outcome_events does (_scan_start) never applies here.
 */

export type SignalRow = {
  id: string;
  symbol: string;
  direction: "long" | "short";
  entry: number;
  stop_loss: number;
  take_profit?: number | null;
  take_profit_1?: number | null;
  take_profit_2?: number | null;
  take_profit_3?: number | null;
  tp1_hit_at?: string | null;
  tp2_hit_at?: string | null;
  tp3_hit_at?: string | null;
  status?: string | null;
  closed_at?: string | null;
};

export type OutcomeEvent = [status: string, closedAt: string];

export const TP_ORDER = ["tp1_hit", "tp2_hit", "tp3_hit"] as const;
export const TERMINAL = new Set(["tp3_hit", "sl_hit", "expired", "tp_hit"]);

/** If a stop arrives after banking TP1+, freeze the highest banked level.
 * Returns the win status to store instead of sl_hit, or null for a pure stop. */
export function stopToPartialWin(
  already: Set<string>,
  events: OutcomeEvent[],
): string | null {
  const hit = new Set(already);
  for (const [name] of events) {
    if ((TP_ORDER as readonly string[]).includes(name) || name === "tp_hit") {
      hit.add(name === "tp_hit" ? "tp1_hit" : name);
    }
  }
  if (hit.has("tp2_hit") || hit.has("tp3_hit")) return "tp2_hit";
  if (hit.has("tp1_hit")) return "tp1_hit";
  return null;
}

/** TP1/TP2/TP3 prices — falls back to single take_profit for legacy rows.
 * Rows where TP2/TP3 were wrongly cloned to equal TP1 collapse to a single
 * target so one touch cannot mark all three levels. */
export function targets(row: SignalRow): number[] {
  const tp1 = row.take_profit_1 ?? row.take_profit;
  const tp2 = row.take_profit_2;
  const tp3 = row.take_profit_3;
  if (tp1 == null) return [];
  const tp1f = Number(tp1);
  if (tp2 == null || tp3 == null) return [tp1f];
  const tp2f = Number(tp2);
  const tp3f = Number(tp3);
  if (tp2f === tp1f && tp3f === tp1f) return [tp1f];
  return [tp1f, tp2f, tp3f];
}

export function alreadyHit(row: SignalRow): Set<string> {
  const status = row.status || "open";
  const hit = new Set<string>();
  if (["tp1_hit", "tp2_hit", "tp3_hit", "tp_hit"].includes(status)) {
    hit.add("tp1_hit");
  }
  if (["tp2_hit", "tp3_hit"].includes(status)) hit.add("tp2_hit");
  if (["tp3_hit", "tp_hit"].includes(status)) hit.add("tp3_hit");
  if (row.tp1_hit_at) hit.add("tp1_hit");
  if (row.tp2_hit_at) hit.add("tp2_hit");
  if (row.tp3_hit_at) hit.add("tp3_hit");
  return hit;
}

/** Ordered new events for this tick: [status, closedAtIso][].
 * Stop wins on a tie with any TP. A fast move can cross multiple unhit TPs
 * in one tick — all are returned in order. */
export function checkTickOutcome(
  row: SignalRow,
  price: number,
  closedAtIso: string,
): OutcomeEvent[] {
  const isLong = row.direction === "long";
  const stop = Number(row.stop_loss);
  const entry = Number(row.entry);
  const tps = targets(row);
  const already = alreadyHit(row);
  const events: OutcomeEvent[] = [];

  const levelNames = tps.length === 1 ? ["tp_hit"] : TP_ORDER.slice(0, tps.length);
  const finalName = levelNames[levelNames.length - 1];

  const closedOut = () =>
    already.has(finalName) || events.some(([name]) => name === finalName);

  const activeStop = () => {
    const banked =
      [...already].some((h) => (TP_ORDER as readonly string[]).includes(h)) ||
      events.some(([name]) => (TP_ORDER as readonly string[]).includes(name) || name === "tp_hit");
    return banked ? entry : stop;
  };

  if (closedOut()) return events;

  if (isLong) {
    if (price <= activeStop()) {
      events.push(["sl_hit", closedAtIso]);
      return events;
    }
    for (let i = 0; i < tps.length; i++) {
      const name = levelNames[i];
      if (already.has(name) || events.some(([n]) => n === name)) continue;
      if (price >= tps[i]) events.push([name, closedAtIso]);
    }
  } else {
    if (price >= activeStop()) {
      events.push(["sl_hit", closedAtIso]);
      return events;
    }
    for (let i = 0; i < tps.length; i++) {
      const name = levelNames[i];
      if (already.has(name) || events.some(([n]) => n === name)) continue;
      if (price <= tps[i]) events.push([name, closedAtIso]);
    }
  }
  return events;
}
