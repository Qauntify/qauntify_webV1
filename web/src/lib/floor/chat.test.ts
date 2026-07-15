import { describe, expect, it } from "vitest";

import { allowFloorChat } from "./chat";

describe("allowFloorChat", () => {
  it("allows first messages then blocks within the window", () => {
    const now = 1_000_000;
    const timestamps: number[] = [];

    for (let index = 0; index < 6; index += 1) {
      expect(allowFloorChat(timestamps, now + index * 1_000, 6, 60_000)).toBe(true);
      timestamps.push(now + index * 1_000);
    }

    expect(allowFloorChat(timestamps, now + 7_000, 6, 60_000)).toBe(false);
  });
});
