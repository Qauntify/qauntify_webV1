export const FLOOR_DESKS = ["macro", "technical", "news", "pm"] as const;
export type FloorDesk = (typeof FLOOR_DESKS)[number];

export const FLOOR_TONES = ["bullish", "neutral", "cautious"] as const;
export type FloorTone = (typeof FLOOR_TONES)[number];

export const GOLD_SYMBOL = "PAXGUSDT";

export type FloorBrief = {
  id: string;
  desk: FloorDesk;
  tone: FloorTone;
  body: string;
  runId: string;
  createdAt: string;
};

export type DeskBriefResult = { tone: FloorTone; body: string };

export type PmDecisionResult = {
  action: "signal" | "pass";
  tone: FloorTone;
  body: string;
  direction?: "long" | "short";
  entry?: number;
  stopLoss?: number;
  takeProfit?: number;
  confidence?: number;
};

export type FloorGoldSignal = {
  direction: "long" | "short";
  entry: number;
  stopLoss: number;
  takeProfit: number;
  confidence: number;
  body: string;
  createdAt: string;
};

export type FloorRunPhase =
  | "idle"
  | "macro"
  | "technical"
  | "news"
  | "pm"
  | "sleeping";

export type FloorRunStatus = {
  running: boolean;
  runId: string | null;
  cycle: number;
  phase: FloorRunPhase;
  lastMessage: string;
  lastSignal: FloorGoldSignal | null;
};

export type GoldScanOutcome = {
  timeframe: string;
  status: string;
  direction?: string;
  confidence?: number;
  entry?: number;
  stopLoss?: number;
  takeProfit?: number;
  rationale?: string;
  alerted?: boolean;
};

export type GoldScanResult = {
  ok: boolean;
  error?: string;
  runId?: string;
  symbol?: string;
  stored?: number;
  alerted?: boolean;
  headlines?: string[];
  outcomes?: GoldScanOutcome[];
};
