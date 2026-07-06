import { describe, expect, it } from "vitest";

import { formatPrice, formatRelativeTime } from "./format";

describe("formatPrice", () => {
  it("uses no decimals for large prices", () => {
    expect(formatPrice(108240)).toBe("108,240");
  });

  it("uses two decimals for small prices", () => {
    expect(formatPrice(3.5)).toBe("3.50");
  });
});

describe("formatRelativeTime", () => {
  const now = new Date("2026-07-06T12:00:00Z");

  it("renders minutes", () => {
    expect(formatRelativeTime("2026-07-06T11:45:00Z", now)).toBe("15m ago");
  });

  it("renders hours", () => {
    expect(formatRelativeTime("2026-07-06T09:00:00Z", now)).toBe("3h ago");
  });

  it("renders days", () => {
    expect(formatRelativeTime("2026-07-04T09:00:00Z", now)).toBe("2d ago");
  });

  it("handles invalid dates gracefully", () => {
    expect(formatRelativeTime("garbage", now)).toBe("just now");
  });
});
