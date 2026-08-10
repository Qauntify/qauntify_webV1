/** Public tools library — MT5 EAs, indicators, TradingView links. */

export const TOOL_CATEGORIES = [
  { id: "mt5_ea", labelEn: "MT5 Expert Advisor", labelKm: "MT5 EA" },
  { id: "mt5_indicator", labelEn: "MT5 Indicator", labelKm: "MT5 Indicator" },
  { id: "tradingview", labelEn: "TradingView", labelKm: "TradingView" },
  { id: "other", labelEn: "Other", labelKm: "ផ្សេងៗ" },
] as const;

export type ToolCategory = (typeof TOOL_CATEGORIES)[number]["id"];

export type Tool = {
  id: string;
  titleKm: string;
  descriptionKm: string;
  category: ToolCategory;
  fileUrl: string | null;
  fileName: string | null;
  mimeType: string | null;
  fileSize: number | null;
  externalUrl: string | null;
  sortOrder: number;
  published: boolean;
  createdAt: string;
  updatedAt: string;
};

type ToolRow = {
  id: string;
  title_km: string;
  description_km: string;
  category: string;
  file_url: string | null;
  file_name: string | null;
  mime_type: string | null;
  file_size: number | null;
  external_url: string | null;
  sort_order: number;
  published: boolean;
  created_at: string;
  updated_at: string;
};

const CATEGORY_IDS = new Set<string>(TOOL_CATEGORIES.map((c) => c.id));

export function parseToolCategory(value: string): ToolCategory {
  const v = value.trim().toLowerCase();
  if (CATEGORY_IDS.has(v)) return v as ToolCategory;
  return "other";
}

export function parseToolRow(row: ToolRow): Tool | null {
  if (!row?.id || typeof row.title_km !== "string") return null;
  return {
    id: row.id,
    titleKm: row.title_km,
    descriptionKm: typeof row.description_km === "string" ? row.description_km : "",
    category: parseToolCategory(row.category ?? "other"),
    fileUrl: typeof row.file_url === "string" ? row.file_url : null,
    fileName: typeof row.file_name === "string" ? row.file_name : null,
    mimeType: typeof row.mime_type === "string" ? row.mime_type : null,
    fileSize:
      typeof row.file_size === "number" && Number.isFinite(row.file_size)
        ? row.file_size
        : null,
    externalUrl: typeof row.external_url === "string" ? row.external_url : null,
    sortOrder: Number.isFinite(row.sort_order) ? row.sort_order : 0,
    published: row.published === true,
    createdAt: row.created_at,
    updatedAt: row.updated_at,
  };
}

export function toolCategoryLabelKm(category: ToolCategory): string {
  return TOOL_CATEGORIES.find((c) => c.id === category)?.labelKm ?? category;
}

export function formatToolFileSize(bytes: number | null): string | null {
  if (bytes == null || bytes <= 0) return null;
  if (bytes < 1024) return String(bytes) + " B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
  return (bytes / (1024 * 1024)).toFixed(1) + " MB";
}

function supabaseConfig(): { url: string; anonKey: string } | null {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !anonKey) return null;
  return { url: url.replace(/\/$/, ""), anonKey };
}

function anonHeaders(anonKey: string): HeadersInit {
  return {
    apikey: anonKey,
    Authorization: "Bearer " + anonKey,
  };
}

const TOOL_SELECT =
  "id,title_km,description_km,category,file_url,file_name,mime_type,file_size,external_url,sort_order,published,created_at,updated_at";

/** Published tools for the public /tools page (anon + RLS). */
export async function getPublishedTools(): Promise<Tool[]> {
  const cfg = supabaseConfig();
  if (!cfg) return [];
  try {
    const url =
      cfg.url +
      "/rest/v1/tools?published=eq.true&select=" +
      TOOL_SELECT +
      "&order=sort_order.asc,created_at.desc";
    const response = await fetch(url, {
      headers: anonHeaders(cfg.anonKey),
      cache: "no-store",
    });
    if (!response.ok) return [];
    const rows = (await response.json()) as ToolRow[];
    if (!Array.isArray(rows)) return [];
    return rows.map(parseToolRow).filter((t): t is Tool => t != null);
  } catch {
    return [];
  }
}

/** Download href for a tool — file or external link. */
export function toolDownloadHref(tool: Tool): string | null {
  if (tool.externalUrl) return tool.externalUrl;
  if (tool.fileUrl) return tool.fileUrl;
  return null;
}

export function toolIsExternal(tool: Tool): boolean {
  return Boolean(tool.externalUrl && !tool.fileUrl);
}
