import { describe, expect, it } from "vitest";

import { floorCronAuthorized } from "./auth";

describe("floorCronAuthorized", () => {
  it("accepts Bearer secret", () => {
    const request = new Request("https://x/api/cron/floor", {
      headers: { authorization: "Bearer s3cret" },
    });

    expect(floorCronAuthorized(request, "s3cret")).toBe(true);
  });

  it("accepts query secret", () => {
    const request = new Request("https://x/api/cron/floor?secret=s3cret");

    expect(floorCronAuthorized(request, "s3cret")).toBe(true);
  });

  it("rejects empty configured secret", () => {
    const request = new Request("https://x/api/cron/floor?secret=s3cret");

    expect(floorCronAuthorized(request, "")).toBe(false);
  });
});
