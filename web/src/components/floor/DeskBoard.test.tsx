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
  it("shows the dealing room on standby when no briefs exist", () => {
    render(<DeskBoard desks={[]} />);

    expect(screen.getByText("Institutional Trading Floor")).toBeDefined();
    expect(screen.getByText("Desks on standby")).toBeDefined();
    expect(screen.getAllByText("Console on standby for the next floor run.")).toHaveLength(4);
  });

  it("orders all desk stations and fills missing desks", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-07-15T14:00:00.000Z"));

    render(<DeskBoard desks={[MACRO_BRIEF]} />);

    expect(screen.getByText("Macro desk")).toBeDefined();
    expect(screen.getByText("Technical desk")).toBeDefined();
    expect(screen.getByText("News desk")).toBeDefined();
    expect(screen.getByText("PM / Risk")).toBeDefined();
    expect(screen.getByText("bullish")).toBeDefined();
    expect(screen.getByText("Dollar liquidity is improving.")).toBeDefined();
    expect(screen.getAllByText("Console on standby for the next floor run.")).toHaveLength(3);
    expect(screen.getByText("1/4 desks live")).toBeDefined();

    const timestamp = screen.getByText(formatRelativeTime(MACRO_BRIEF.createdAt));
    expect(timestamp).toBeDefined();
    expect(timestamp.getAttribute("dateTime")).toBe(MACRO_BRIEF.createdAt);
  });
});
