import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TradingFloor } from "./TradingFloor";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("TradingFloor", () => {
  it("loads the gold floor board and shows run controls", async () => {
    vi.stubGlobal("fetch", vi.fn((url: string) => {
      if (url === "/api/floor/board") {
        return Promise.resolve(new Response(JSON.stringify({
          symbol: "PAXGUSDT",
          desks: [{
            id: "macro-1",
            desk: "macro",
            tone: "neutral",
            body: "Gold range-bound ahead of US data.",
            runId: "run-1",
            createdAt: "2026-07-15T12:00:00.000Z",
          }],
          lastSignal: null,
          scanLine: "Press Run to start the gold AI hunter.",
        })));
      }
      if (url === "/api/admin/floor/run") {
        return Promise.resolve(new Response(JSON.stringify({
          running: false,
          runId: null,
          cycle: 0,
          phase: "idle",
          lastMessage: "",
          lastSignal: null,
        })));
      }
      return Promise.resolve(new Response(JSON.stringify({})));
    }));

    render(<TradingFloor />);

    expect(await screen.findByText("Gold floor — PAXGUSDT")).toBeDefined();
    expect(screen.getByRole("button", { name: "Run" })).toBeDefined();
  });
});
