import { afterEach, describe, expect, it, vi } from "vitest";

import { dispatchEngineWorkflow } from "./github-engine";

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
