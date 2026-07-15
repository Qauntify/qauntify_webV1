import { describe, expect, it } from "vitest";
import { parseDeskBrief } from "./llm";

describe("parseDeskBrief", () => {
  it("parses tone and body", () => {
    const out = parseDeskBrief(
      '{"tone":"cautious","body":"London open with USD high-impact ahead."}',
    );
    expect(out).toEqual({
      tone: "cautious",
      body: "London open with USD high-impact ahead.",
    });
  });

  it("rejects invalid tone to neutral with truncated body fallback", () => {
    const out = parseDeskBrief('{"tone":"yolo","body":"ok"}');
    expect(out.tone).toBe("neutral");
    expect(out.body).toBe("ok");
  });

  it("fail-closes on garbage", () => {
    const out = parseDeskBrief("not json");
    expect(out.tone).toBe("neutral");
    expect(out.body.length).toBeGreaterThan(0);
  });
});
