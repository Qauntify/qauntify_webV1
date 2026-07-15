import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TradingFloor } from "./TradingFloor";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("TradingFloor", () => {
  it("loads the desk board above the PM chat", async () => {
    vi.stubGlobal("fetch", vi.fn((url: string) => {
      if (url === "/api/floor/board") {
        return Promise.resolve(new Response(JSON.stringify({
        desks: [{
          id: "macro-1",
          desk: "macro",
          tone: "neutral",
          body: "Macro remains range-bound.",
          runId: "run-1",
          createdAt: "2026-07-15T12:00:00.000Z",
        }],
        })));
      }
      return Promise.resolve(new Response(JSON.stringify({ messages: [] })));
    }));

    render(<TradingFloor />);

    expect(await screen.findByText("Macro remains range-bound.")).toBeDefined();
    expect(screen.getByRole("region", { name: "Floor PM chat" })).toBeDefined();
  });
});
