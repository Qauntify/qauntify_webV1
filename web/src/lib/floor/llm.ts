import type { DeskBriefResult, FloorTone } from "./types";
import { FLOOR_TONES } from "./types";

const MAX_BODY = 600;

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
  opts?: { temperature?: number },
): Promise<string> {
  const apiKey = process.env.FLOOR_LLM_API_KEY?.trim();
  const baseUrl = (process.env.FLOOR_LLM_BASE_URL || "https://api.openai.com/v1").replace(/\/$/, "");
  const model = process.env.FLOOR_LLM_MODEL?.trim();
  if (!apiKey || !model) {
    throw new Error("FLOOR_LLM_API_KEY and FLOOR_LLM_MODEL must be set");
  }
  const res = await fetch(`${baseUrl}/chat/completions`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model,
      temperature: opts?.temperature ?? 0.3,
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
