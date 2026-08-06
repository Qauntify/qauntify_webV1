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
  { id: "all", label: "All", hint: "Every session" },
  { id: "war-room", label: "War Room", hint: "Floor-decided only" },
  { id: "super-scalping", label: "Super scalp (5m)", hint: "ICT FVG" },
  { id: "scalping", label: "Scalping (15m)", hint: "Cloud + MSS" },
  { id: "swing", label: "Swing (1h)", hint: "AI-confirmed" },
  { id: "bbma", label: "BBMA", hint: "XAU live EA" },
];

export const ADMIN_SIGNAL_FILTER_OPTIONS: SignalFilterOption[] = [
  { id: "all", label: "All", hint: "Every stored signal" },
  { id: "llm", label: "LLM", hint: "SEA-LION confirmed" },
  { id: "war-room", label: "War Room", hint: "Floor-decided only" },
  { id: "super-scalping", label: "Super scalp (5m)", hint: "ICT FVG" },
  { id: "scalping", label: "Scalping (15m)", hint: "Cloud + MSS" },
  { id: "swing", label: "Swing (1h)", hint: "AI-confirmed" },
  { id: "bbma", label: "BBMA", hint: "XAU live EA" },
];
