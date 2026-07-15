import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { formatRelativeTime } from "@/lib/format";
import type { FloorBrief } from "@/lib/floor/types";
import { DeskBoard } from "./DeskBoard";

const MACRO_BRIEF: FloorBrief = {
  id: "macro-1",
  desk: "macro",
  tone: "bullish",
  body: "Dollar liquidity is improving.",
  runId: "run-1",
  createdAt: "2026-07-15T12:00:00.000Z",
};

afterEach(() => {
  vi.useRealTimers();
});

describe("DeskBoard", () => {
  it("explains when the floor has not posted a brief", () => {
    render(<DeskBoard desks={[]} />);

    expect(screen.getByText("Desks warming up")).toBeDefined();
    expect(screen.getByText(/floor cron has not posted yet/i)).toBeDefined();
  });

  it("orders all desk cards and fills missing desks", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-07-15T14:00:00.000Z"));

    render(<DeskBoard desks={[MACRO_BRIEF]} />);

    expect(screen.getByText("Macro")).toBeDefined();
    expect(screen.getByText("Technical")).toBeDefined();
    expect(screen.getByText("News")).toBeDefined();
    expect(screen.getByText("PM")).toBeDefined();
    expect(screen.getByText("bullish")).toBeDefined();
    expect(screen.getByText("Dollar liquidity is improving.")).toBeDefined();
    expect(screen.getAllByText("—")).toHaveLength(3);

    const timestamp = screen.getByText(formatRelativeTime(MACRO_BRIEF.createdAt));
    expect(timestamp).toBeDefined();
    expect(timestamp.getAttribute("dateTime")).toBe(MACRO_BRIEF.createdAt);
  });
});
