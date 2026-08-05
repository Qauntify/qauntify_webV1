/** TS mirror of signals/outcome_tracker.py:apply_events, minus the chart
 * step (never ported — see docs/plan). Same per-event loop: claim (race-safe
 * against the slow Python cron), reclassify a stop-after-TP1 as a win, alert
 * Telegram only on a won claim. */
import { formatOutcomeAlert } from "./outcome-alert";
import { alreadyHit, stopToPartialWin, TERMINAL, type OutcomeEvent, type SignalRow } from "./outcome-rules";

export type ApplyTickDeps = {
  updateSignalOutcomeClaim: (
    id: string,
    status: string,
    at: string,
    opts: { terminal: boolean; expectedStatus: string },
  ) => Promise<boolean>;
  sendTelegramMessage: (text: string, botToken: string, chatId: string) => Promise<void>;
  telegramBotToken: string;
  telegramChannelId: string;
};

const ALERTABLE = new Set(["tp1_hit", "tp2_hit", "tp3_hit", "tp_hit", "sl_hit"]);

export async function applyTickEvents(
  initialRow: SignalRow,
  events: OutcomeEvent[],
  deps: ApplyTickDeps,
): Promise<{ row: SignalRow; latest: string | null }> {
  let row = initialRow;
  let latest: string | null = null;
  const applied: OutcomeEvent[] = [];

  for (const [initialOutcome, closedAt] of events) {
    let outcome = initialOutcome;
    let freezeOnly = false;
    const priorStatus = row.status || "open";
    let terminal: boolean;

    if (outcome === "sl_hit") {
      const locked = stopToPartialWin(alreadyHit(row), applied);
      if (locked !== null) {
        outcome = locked;
        terminal = true;
        freezeOnly = true;
      } else {
        terminal = true;
      }
    } else {
      terminal = TERMINAL.has(outcome);
    }

    let claimed: boolean;
    try {
      claimed = await deps.updateSignalOutcomeClaim(row.id, outcome, closedAt, {
        terminal,
        expectedStatus: priorStatus,
      });
    } catch {
      break; // failed to persist -- stop here, the slow cron will retry
    }
    if (!claimed) break; // another writer already applied this event

    latest = outcome;
    row = { ...row, status: outcome };
    if (terminal) row = { ...row, closed_at: closedAt };

    if (!freezeOnly && ALERTABLE.has(outcome) && deps.telegramBotToken && deps.telegramChannelId) {
      try {
        await deps.sendTelegramMessage(
          formatOutcomeAlert(row, outcome),
          deps.telegramBotToken,
          deps.telegramChannelId,
        );
      } catch {
        // best-effort -- the status write already succeeded
      }
    }
    applied.push([outcome, closedAt]);
  }

  return { row, latest };
}
