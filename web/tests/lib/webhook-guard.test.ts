import { afterEach, describe, expect, it } from "vitest";

import { authorizedBySecret } from "@/lib/webhook-guard";

afterEach(() => {
  delete process.env.TEST_SECRET;
});

describe("authorizedBySecret", () => {
  it("rejects when the env var isn't set", () => {
    const req = new Request("https://x.test/hook", {
      headers: { authorization: "Bearer anything" },
    });
    expect(authorizedBySecret(req, "TEST_SECRET")).toBe(false);
  });

  it("accepts a matching Authorization header", () => {
    process.env.TEST_SECRET = "s3cr3t";
    const req = new Request("https://x.test/hook", {
      headers: { authorization: "Bearer s3cr3t" },
    });
    expect(authorizedBySecret(req, "TEST_SECRET")).toBe(true);
  });

  it("rejects a mismatched header", () => {
    process.env.TEST_SECRET = "s3cr3t";
    const req = new Request("https://x.test/hook", {
      headers: { authorization: "Bearer wrong" },
    });
    expect(authorizedBySecret(req, "TEST_SECRET")).toBe(false);
  });

  it("ignores a correct query secret unless allowQuerySecret is set", () => {
    process.env.TEST_SECRET = "s3cr3t";
    const req = new Request("https://x.test/hook?secret=s3cr3t");
    expect(authorizedBySecret(req, "TEST_SECRET")).toBe(false);
  });

  it("accepts a matching query secret when allowQuerySecret is set", () => {
    process.env.TEST_SECRET = "s3cr3t";
    const req = new Request("https://x.test/hook?secret=s3cr3t");
    expect(authorizedBySecret(req, "TEST_SECRET", { allowQuerySecret: true })).toBe(true);
  });
});
