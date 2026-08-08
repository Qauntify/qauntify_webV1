export type SignalsBrowseTab = "all" | "ai" | "bbma";

/** Sub-filter within the AI Signal tab — one strategy or every strategy. */
export type AiSignalStrategy =
  | "all"
  | "war-room"
  | "super-scalping"
  | "scalping"
  | "swing";

export type SignalFilterOption = {
  id: string;
  label: string;
  hint: string;
  /** Compact lane code for the session rail (e.g. 5M). */
  code?: string;
  /** Shown but not selectable — a "coming soon" placeholder strategy. */
  disabled?: boolean;
};

export function parseSignalsBrowseTab(tab: string | undefined): SignalsBrowseTab {
  if (tab === "ai") return "ai";
  if (tab === "bbma") return "bbma";
  return "all";
}

export function parseAiSignalStrategy(
  strategy: string | undefined,
): AiSignalStrategy {
  if (strategy === "war-room") return "war-room";
  if (strategy === "super-scalping") return "super-scalping";
  if (strategy === "scalping") return "scalping";
  if (strategy === "swing") return "swing";
  return "all";
}

export const SIGNAL_FILTER_OPTIONS: SignalFilterOption[] = [
  { id: "all", label: "All", hint: "Every session", code: "ALL" },
  { id: "ai", label: "AI Signal", hint: "SEA-LION confirmed", code: "AI" },
  { id: "bbma", label: "BBMA", hint: "XAU live EA", code: "BBMA" },
  { id: "ict", label: "ICT", hint: "Coming soon", code: "ICT", disabled: true },
  { id: "smc", label: "SMC", hint: "Coming soon", code: "SMC", disabled: true },
  {
    id: "supply-demand",
    label: "Supply Demand",
    hint: "Coming soon",
    code: "S/D",
    disabled: true,
  },
  { id: "crt", label: "CRT", hint: "Coming soon", code: "CRT", disabled: true },
  { id: "msnr", label: "MSNR", hint: "Coming soon", code: "MSNR", disabled: true },
];

/** Sub-strategy pills shown inside the AI Signal tab. */
export const AI_SIGNAL_STRATEGY_OPTIONS: SignalFilterOption[] = [
  { id: "all", label: "All", hint: "Every AI strategy", code: "ALL" },
  { id: "war-room", label: "War Room", hint: "Floor debate", code: "WR" },
  { id: "super-scalping", label: "Super scalp", hint: "5m ICT FVG", code: "5M" },
  { id: "scalping", label: "Scalping", hint: "15m cloud + MSS", code: "15M" },
  { id: "swing", label: "Swing", hint: "1h AI confirm", code: "1H" },
];

export const ADMIN_SIGNAL_FILTER_OPTIONS: SignalFilterOption[] = [
  { id: "all", label: "All", hint: "Every stored signal", code: "ALL" },
  { id: "llm", label: "LLM", hint: "SEA-LION confirmed", code: "LLM" },
  { id: "war-room", label: "War Room", hint: "Floor-decided only", code: "WR" },
  { id: "super-scalping", label: "Super scalp (5m)", hint: "ICT FVG", code: "5M" },
  { id: "scalping", label: "Scalping (15m)", hint: "Cloud + MSS", code: "15M" },
  { id: "swing", label: "Swing (1h)", hint: "AI-confirmed", code: "1H" },
  { id: "bbma", label: "BBMA", hint: "XAU live EA", code: "BBMA" },
];
