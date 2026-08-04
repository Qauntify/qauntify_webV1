import { describe, expect, it, vi } from "vitest";

import { applyTickEvents } from "@/lib/outcome-apply";
import type { OutcomeEvent, SignalRow } from "@/lib/outcome-rules";

function row(overrides: Partial<SignalRow> = {}): SignalRow {
  return {
    id: "sig-1",
    symbol: "XAUUSD",
    direction: "long",
    entry: 100.0,
    stop_loss: 95.0,
    take_profit_1: 105.0,
    take_profit_2: 110.0,
    take_profit_3: 115.0,
    status: "open",
    ...overrides,
  };
}

function deps(claimResults: boolean[]) {
  let i = 0;
  const claims: Array<{ status: string; expectedStatus: string }> = [];
  const alerts: string[] = [];
  return {
    updateSignalOutcomeClaim: vi.fn(async (_id, status, _at, opts) => {
      claims.push({ status, expectedStatus: opts.expectedStatus });
      return claimResults[i++];
    }),
    sendTelegramMessage: vi.fn(async (text: string) => {
      alerts.push(text);
    }),
    telegramBotToken: "bot-token",
    telegramChannelId: "chat-id",
    claims,
    alerts,
  };
}

describe("applyTickEvents", () => {
  it("claims and alerts on a single terminal event", async () => {
    const d = deps([true]);
    const events: OutcomeEvent[] = [["sl_hit", "2026-08-04T12:00:00Z"]];

    const { row: finalRow, latest } = await applyTickEvents(row(), events, d);

    expect(latest).toBe("sl_hit");
    expect(finalRow.status).toBe("sl_hit");
    expect(finalRow.closed_at).toBe("2026-08-04T12:00:00Z");
    expect(d.claims).toEqual([{ status: "sl_hit", expectedStatus: "open" }]);
    expect(d.alerts).toHaveLength(1);
  });

  it("stops applying further events and skips the alert once a claim fails", async () => {
    const d = deps([true, false]);
    const events: OutcomeEvent[] = [
      ["tp1_hit", "2026-08-04T12:00:00Z"],
      ["tp2_hit", "2026-08-04T12:05:00Z"],
    ];

    const { row: finalRow, latest } = await applyTickEvents(row(), events, d);

    expect(latest).toBe("tp1_hit");
    expect(finalRow.status).toBe("tp1_hit");
    expect(d.claims).toEqual([
      { status: "tp1_hit", expectedStatus: "open" },
      { status: "tp2_hit", expectedStatus: "tp1_hit" },
    ]);
    expect(d.alerts).toHaveLength(1); // tp2_hit never alerted -- lost the race
  });

  it("reclassifies a stop after TP1 was banked as a win, and does not double-alert", async () => {
    const d = deps([true, true]);
    const events: OutcomeEvent[] = [
      ["tp1_hit", "2026-08-04T12:00:00Z"],
      ["sl_hit", "2026-08-04T12:05:00Z"],
    ];

    const { row: finalRow, latest } = await applyTickEvents(row(), events, d);

    // sl_hit after TP1 is banked freezes as tp1_hit (a win), not a loss.
    expect(latest).toBe("tp1_hit");
    expect(finalRow.status).toBe("tp1_hit");
    expect(d.claims[1].status).toBe("tp1_hit");
    expect(d.alerts).toHaveLength(1); // the freeze itself does not re-alert
  });

  it("returns latest=null and makes no claim when there are no events", async () => {
    const d = deps([]);
    const { latest } = await applyTickEvents(row(), [], d);
    expect(latest).toBeNull();
    expect(d.claims).toEqual([]);
    expect(d.alerts).toEqual([]);
  });
});
