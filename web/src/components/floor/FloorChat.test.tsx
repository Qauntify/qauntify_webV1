import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FloorChat } from "./FloorChat";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("FloorChat", () => {
  it("loads saved messages and appends a sent exchange", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({
        messages: [{
          id: "assistant-1",
          role: "assistant",
          content: "Existing market context.",
          createdAt: "2026-07-15T12:00:00.000Z",
        }],
      })))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        user: {
          id: "user-1",
          role: "user",
          content: "What is the risk?",
          createdAt: "2026-07-15T12:01:00.000Z",
        },
        assistant: {
          id: "assistant-2",
          role: "assistant",
          content: "Keep position size controlled.",
          createdAt: "2026-07-15T12:01:01.000Z",
        },
      })));
    vi.stubGlobal("fetch", fetchMock);

    render(<FloorChat />);

    expect(await screen.findByText("Existing market context.")).toBeDefined();
    fireEvent.change(screen.getByLabelText("Message the floor PM"), {
      target: { value: "What is the risk?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => {
      expect(screen.getByText("Keep position size controlled.")).toBeDefined();
    });
    expect(fetchMock).toHaveBeenLastCalledWith("/api/floor/chat", {
      body: JSON.stringify({ message: "What is the risk?" }),
      headers: { "Content-Type": "application/json" },
      method: "POST",
    });
  });

  it("shows a clear rate-limit message", async () => {
    vi.stubGlobal("fetch", vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ messages: [] })))
      .mockResolvedValueOnce(new Response(
        JSON.stringify({ error: "Too many messages. Please wait a moment." }),
        { status: 429 },
      )));

    render(<FloorChat />);

    await screen.findByRole("button", { name: "Send" });
    fireEvent.change(screen.getByLabelText("Message the floor PM"), {
      target: { value: "Status?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    expect(await screen.findByText("Too many messages. Please wait a moment.")).toBeDefined();
  });
});
