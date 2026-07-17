import type { DeskBriefResult, FloorDesk, FloorTone, PmDecisionResult } from "./types";
import { FLOOR_TONES } from "./types";

const MAX_BODY = 600;

/** Per-desk keys — never reuse SEALION_* confirm keys. */
export const FLOOR_DESK_API_KEY_ENV = {
  macro: "FLOOR_LLM_API_KEY_MACRO",
  technical: "FLOOR_LLM_API_KEY_TECHNICAL",
  news: "FLOOR_LLM_API_KEY_NEWS",
  pm: "FLOOR_LLM_API_KEY_PM",
} as const satisfies Record<FloorDesk, string>;

export function floorApiKeyForDesk(desk: FloorDesk): string {
  const envName = FLOOR_DESK_API_KEY_ENV[desk];
  const key = process.env[envName]?.trim() ?? "";
  if (!key) {
    throw new Error(`${envName} must be set for the ${desk} desk`);
  }
  return key;
}

export function parsePmDecision(text: string): PmDecisionResult {
  const start = text.indexOf("{");
  const end = text.lastIndexOf("}");
  if (start === -1 || end <= start) {
    return { action: "pass", tone: "neutral", body: "PM unavailable (unparseable reply)." };
  }
  try {
    const data = JSON.parse(text.slice(start, end + 1)) as {
      action?: string;
      tone?: string;
      body?: string;
      direction?: string;
      entry?: number;
      stopLoss?: number;
      takeProfit?: number;
      confidence?: number;
    };
    const tone = (FLOOR_TONES as readonly string[]).includes(data.tone ?? "")
      ? (data.tone as FloorTone)
      : "neutral";
    const body = String(data.body ?? "").trim().slice(0, MAX_BODY)
      || "PM returned an empty note.";
    const action = data.action === "signal" ? "signal" : "pass";
    const direction = data.direction === "long" || data.direction === "short"
      ? data.direction
      : undefined;
    return {
      action,
      tone,
      body,
      direction,
      entry: typeof data.entry === "number" ? data.entry : undefined,
      stopLoss: typeof data.stopLoss === "number" ? data.stopLoss : undefined,
      takeProfit: typeof data.takeProfit === "number" ? data.takeProfit : undefined,
      confidence: typeof data.confidence === "number" ? data.confidence : undefined,
    };
  } catch {
    return { action: "pass", tone: "neutral", body: "PM unavailable (invalid JSON)." };
  }
}

export function parseDeskBrief(text: string): DeskBriefResult {
  const start = text.indexOf("{");
  const end = text.lastIndexOf("}");
  if (start === -1 || end <= start) {
    return { tone: "neutral", body: "Desk unavailable (unparseable reply)." };
  }
  try {
    const data = JSON.parse(text.slice(start, end + 1)) as {
      tone?: string;
      body?: string;
    };
    const tone = (FLOOR_TONES as readonly string[]).includes(data.tone ?? "")
      ? (data.tone as FloorTone)
      : "neutral";
    const body = String(data.body ?? "").trim().slice(0, MAX_BODY)
      || "Desk returned an empty brief.";
    return { tone, body };
  } catch {
    return { tone: "neutral", body: "Desk unavailable (invalid JSON)." };
  }
}

export async function floorChat(
  messages: { role: "system" | "user" | "assistant"; content: string }[],
  opts: { desk: FloorDesk; temperature?: number },
): Promise<string> {
  const apiKey = floorApiKeyForDesk(opts.desk);
  const baseUrl = (process.env.FLOOR_LLM_BASE_URL || "https://api.openai.com/v1").replace(/\/$/, "");
  const model = process.env.FLOOR_LLM_MODEL?.trim();
  if (!model) {
    throw new Error("FLOOR_LLM_MODEL must be set");
  }
  const res = await fetch(`${baseUrl}/chat/completions`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model,
      temperature: opts.temperature ?? 0.3,
      messages,
      response_format: { type: "json_object" },
    }),
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(`Floor LLM HTTP ${res.status}: ${detail.slice(0, 200)}`);
  }
  const json = (await res.json()) as {
    choices?: { message?: { content?: string } }[];
  };
  return json.choices?.[0]?.message?.content ?? "";
}
