import { afterEach, describe, expect, it, vi } from "vitest";

import {
  dispatchEngineWorkflow,
  dispatchHealthcheckWorkflow,
  dispatchWarRoomWorkflow,
  dispatchXauScalperRestart,
} from "@/lib/github-engine";

describe("dispatchEngineWorkflow", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    delete process.env.GITHUB_DISPATCH_TOKEN;
    delete process.env.GITHUB_REPO;
  });

  it("returns error when token is missing", async () => {
    const result = await dispatchEngineWorkflow();
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.message).toContain("GITHUB_DISPATCH_TOKEN");
    }
  });

  it("dispatches workflow on success", async () => {
    process.env.GITHUB_DISPATCH_TOKEN = "ghp_test";
    const fetchMock = vi.fn().mockResolvedValue({ status: 204, text: async () => "" });
    vi.stubGlobal("fetch", fetchMock);

    const result = await dispatchEngineWorkflow();
    expect(result.ok).toBe(true);
    expect(fetchMock).toHaveBeenCalledWith(
      "https://api.github.com/repos/Qauntify/qauntify_webV1/actions/workflows/engine.yml/dispatches",
      expect.objectContaining({ method: "POST" }),
    );
  });
});

describe("dispatchXauScalperRestart", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    delete process.env.GITHUB_DISPATCH_TOKEN;
    delete process.env.GITHUB_REPO;
  });

  it("returns error when token is missing", async () => {
    const result = await dispatchXauScalperRestart();
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.message).toContain("GITHUB_DISPATCH_TOKEN");
    }
  });

  it("dispatches a run-xau-scalper repository_dispatch event on success", async () => {
    process.env.GITHUB_DISPATCH_TOKEN = "ghp_test";
    const fetchMock = vi.fn().mockResolvedValue({ status: 204, text: async () => "" });
    vi.stubGlobal("fetch", fetchMock);

    const result = await dispatchXauScalperRestart();
    expect(result.ok).toBe(true);
    expect(fetchMock).toHaveBeenCalledWith(
      "https://api.github.com/repos/Qauntify/qauntify_webV1/dispatches",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ event_type: "run-xau-scalper" }),
      }),
    );
  });
});

describe("dispatchWarRoomWorkflow", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    delete process.env.GITHUB_DISPATCH_TOKEN;
  });

  it("dispatches run-war-room", async () => {
    process.env.GITHUB_DISPATCH_TOKEN = "ghp_test";
    const fetchMock = vi.fn().mockResolvedValue({ status: 204, text: async () => "" });
    vi.stubGlobal("fetch", fetchMock);

    const result = await dispatchWarRoomWorkflow();
    expect(result.ok).toBe(true);
    expect(fetchMock.mock.calls[0][1].body).toBe(
      JSON.stringify({ event_type: "run-war-room" }),
    );
  });
});

describe("dispatchHealthcheckWorkflow", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    delete process.env.GITHUB_DISPATCH_TOKEN;
  });

  it("dispatches run-session-healthcheck", async () => {
    process.env.GITHUB_DISPATCH_TOKEN = "ghp_test";
    const fetchMock = vi.fn().mockResolvedValue({ status: 204, text: async () => "" });
    vi.stubGlobal("fetch", fetchMock);

    const result = await dispatchHealthcheckWorkflow();
    expect(result.ok).toBe(true);
    expect(fetchMock.mock.calls[0][1].body).toBe(
      JSON.stringify({ event_type: "run-session-healthcheck" }),
    );
  });
});

describe("listCronStatuses", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    delete process.env.GITHUB_DISPATCH_TOKEN;
  });

  it("returns errors when token is missing", async () => {
    const { listCronStatuses } = await import("@/lib/github-engine");
    const statuses = await listCronStatuses(1);
    expect(statuses.length).toBeGreaterThan(0);
    expect(statuses.every((s) => s.error?.includes("GITHUB_DISPATCH_TOKEN"))).toBe(
      true,
    );
  });

  it("maps workflow runs", async () => {
    process.env.GITHUB_DISPATCH_TOKEN = "ghp_test";
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        workflow_runs: [
          {
            id: 1,
            name: "Signals engine",
            status: "completed",
            conclusion: "success",
            html_url: "https://github.com/x/y/actions/runs/1",
            created_at: "2026-08-06T00:00:00Z",
            updated_at: "2026-08-06T00:01:00Z",
            run_number: 42,
            event: "workflow_dispatch",
            head_branch: "main",
          },
        ],
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const { listCronStatuses } = await import("@/lib/github-engine");
    const statuses = await listCronStatuses(1);
    expect(statuses[0].runs[0]?.run_number).toBe(42);
    expect(statuses[0].runs[0]?.conclusion).toBe("success");
  });
});
