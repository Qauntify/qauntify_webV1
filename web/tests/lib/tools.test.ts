import { describe, expect, it } from "vitest";

import {
  formatToolFileSize,
  parseToolCategory,
  parseToolRow,
  toolDownloadHref,
  toolIsExternal,
} from "@/lib/tools";

describe("parseToolCategory", () => {
  it("accepts known categories", () => {
    expect(parseToolCategory("mt5_ea")).toBe("mt5_ea");
    expect(parseToolCategory("tradingview")).toBe("tradingview");
  });

  it("falls back to other", () => {
    expect(parseToolCategory("unknown")).toBe("other");
  });
});

describe("parseToolRow", () => {
  it("maps a database row", () => {
    const tool = parseToolRow({
      id: "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      title_km: "BBMA EA",
      description_km: "desc",
      category: "mt5_ea",
      file_url: "https://x/tools/a/file.mq5",
      file_name: "QauntifyBBMA.mq5",
      mime_type: "application/octet-stream",
      file_size: 2048,
      external_url: null,
      sort_order: 1,
      published: true,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    });
    expect(tool?.titleKm).toBe("BBMA EA");
    expect(tool?.fileSize).toBe(2048);
  });
});

describe("toolDownloadHref", () => {
  it("prefers external url", () => {
    const tool = parseToolRow({
      id: "1",
      title_km: "TV",
      description_km: "",
      category: "tradingview",
      file_url: null,
      file_name: null,
      mime_type: null,
      file_size: null,
      external_url: "https://tradingview.com/script/x",
      sort_order: 0,
      published: true,
      created_at: "t",
      updated_at: "t",
    });
    expect(tool).not.toBeNull();
    if (!tool) return;
    expect(toolDownloadHref(tool)).toBe("https://tradingview.com/script/x");
    expect(toolIsExternal(tool)).toBe(true);
  });
});

describe("formatToolFileSize", () => {
  it("formats bytes and kilobytes", () => {
    expect(formatToolFileSize(512)).toBe("512 B");
    expect(formatToolFileSize(2048)).toBe("2.0 KB");
  });
});
