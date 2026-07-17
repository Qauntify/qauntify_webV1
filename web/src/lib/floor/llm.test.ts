import { afterEach, describe, expect, it } from "vitest";

import { floorApiKeyForDesk, parseDeskBrief, parsePmDecision } from "./llm";

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

describe("parsePmDecision", () => {
  it("parses a signal decision", () => {
    const out = parsePmDecision(
      '{"action":"signal","tone":"bullish","body":"Clean breakout","direction":"long","entry":2401,"stopLoss":2395,"takeProfit":2415,"confidence":78}',
    );
    expect(out.action).toBe("signal");
    expect(out.direction).toBe("long");
    expect(out.entry).toBe(2401);
  });

  it("defaults to pass when action is missing", () => {
    const out = parsePmDecision('{"tone":"neutral","body":"No edge"}');
    expect(out.action).toBe("pass");
  });
});

describe("floorApiKeyForDesk", () => {
  afterEach(() => {
    delete process.env.FLOOR_LLM_API_KEY_MACRO;
    delete process.env.FLOOR_LLM_API_KEY_TECHNICAL;
    delete process.env.FLOOR_LLM_API_KEY_NEWS;
    delete process.env.FLOOR_LLM_API_KEY_PM;
  });

  it("reads the dedicated key for each desk", () => {
    process.env.FLOOR_LLM_API_KEY_MACRO = "macro-key";
    process.env.FLOOR_LLM_API_KEY_TECHNICAL = "tech-key";
    process.env.FLOOR_LLM_API_KEY_NEWS = "news-key";
    process.env.FLOOR_LLM_API_KEY_PM = "pm-key";
    expect(floorApiKeyForDesk("macro")).toBe("macro-key");
    expect(floorApiKeyForDesk("technical")).toBe("tech-key");
    expect(floorApiKeyForDesk("news")).toBe("news-key");
    expect(floorApiKeyForDesk("pm")).toBe("pm-key");
  });

  it("throws when a desk key is missing", () => {
    expect(() => floorApiKeyForDesk("macro")).toThrow(/FLOOR_LLM_API_KEY_MACRO/);
  });
});
