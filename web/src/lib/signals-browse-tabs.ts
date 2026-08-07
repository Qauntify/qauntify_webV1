export type SignalsBrowseTab =
  | "all"
  | "war-room"
  | "super-scalping"
  | "scalping"
  | "swing"
  | "bbma";

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
  if (tab === "war-room") return "war-room";
  if (tab === "swing") return "swing";
  if (tab === "scalping") return "scalping";
  if (tab === "super-scalping") return "super-scalping";
  if (tab === "bbma") return "bbma";
  return "all";
}

export const SIGNAL_FILTER_OPTIONS: SignalFilterOption[] = [
  { id: "all", label: "All", hint: "Every session", code: "ALL" },
  { id: "war-room", label: "War Room", hint: "Floor debate", code: "WR" },
  { id: "super-scalping", label: "Super scalp", hint: "5m ICT FVG", code: "5M" },
  { id: "scalping", label: "Scalping", hint: "15m cloud + MSS", code: "15M" },
  { id: "swing", label: "Swing", hint: "1h AI confirm", code: "1H" },
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

export const ADMIN_SIGNAL_FILTER_OPTIONS: SignalFilterOption[] = [
  { id: "all", label: "All", hint: "Every stored signal", code: "ALL" },
  { id: "llm", label: "LLM", hint: "SEA-LION confirmed", code: "LLM" },
  { id: "war-room", label: "War Room", hint: "Floor-decided only", code: "WR" },
  { id: "super-scalping", label: "Super scalp (5m)", hint: "ICT FVG", code: "5M" },
  { id: "scalping", label: "Scalping (15m)", hint: "Cloud + MSS", code: "15M" },
  { id: "swing", label: "Swing (1h)", hint: "AI-confirmed", code: "1H" },
  { id: "bbma", label: "BBMA", hint: "XAU live EA", code: "BBMA" },
];
