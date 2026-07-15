export const FLOOR_DESKS = ["macro", "technical", "news", "pm"] as const;
export type FloorDesk = (typeof FLOOR_DESKS)[number];

export const FLOOR_TONES = ["bullish", "neutral", "cautious"] as const;
export type FloorTone = (typeof FLOOR_TONES)[number];

export type FloorBrief = {
  id: string;
  desk: FloorDesk;
  tone: FloorTone;
  body: string;
  runId: string;
  createdAt: string;
};

export type FloorChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  createdAt: string;
};

export type DeskBriefResult = { tone: FloorTone; body: string };
