import { afterEach, describe, expect, it, vi } from "vitest";

import { formatCronFailAlert, sendOpsTelegram } from "@/lib/telegram-ops";

describe("formatCronFailAlert", () => {
  it("includes job and why", () => {
    const text = formatCronFailAlert({
      job: "signals-engine",
      detail: "GITHUB_DISPATCH_TOKEN is not set",
      status: 500,
    });
    expect(text).toContain("Cron failed");
    expect(text).toContain("signals-engine");
    expect(text).toContain("GITHUB_DISPATCH_TOKEN");
    expect(text).toContain("500");
  });

  it("escapes html in detail", () => {
    const text = formatCronFailAlert({
      job: "x",
      detail: "<script>alert(1)</script>",
    });
    expect(text).not.toContain("<script>");
    expect(text).toContain("&lt;script&gt;");
  });
});

describe("sendOpsTelegram", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    delete process.env.TELEGRAM_BOT_TOKEN;
    delete process.env.TELEGRAM_ALERTS_CHAT_ID;
  });

  it("no-ops when alerts chat is missing", async () => {
    process.env.TELEGRAM_BOT_TOKEN = "tok";
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    expect(await sendOpsTelegram("hi")).toBe(false);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("posts to alerts chat id", async () => {
    process.env.TELEGRAM_BOT_TOKEN = "tok";
    process.env.TELEGRAM_ALERTS_CHAT_ID = "-100999";
    const fetchMock = vi.fn().mockResolvedValue({ ok: true });
    vi.stubGlobal("fetch", fetchMock);

    expect(await sendOpsTelegram("hi")).toBe(true);
    expect(fetchMock).toHaveBeenCalledWith(
      "https://api.telegram.org/bottok/sendMessage",
      expect.objectContaining({ method: "POST" }),
    );
    const body = JSON.parse(fetchMock.mock.calls[0][1].body as string);
    expect(body.chat_id).toBe("-100999");
  });
});
