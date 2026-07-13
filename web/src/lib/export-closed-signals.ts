import { jsPDF } from "jspdf";
import autoTable from "jspdf-autotable";
import * as XLSX from "xlsx";

import type { Signal } from "@/lib/signals";

export type ExportTab = "all" | "scalping" | "swing";

export function timeframeForTab(tab: ExportTab): string | undefined {
  if (tab === "scalping") return "15m";
  if (tab === "swing") return "1h";
  return undefined;
}

export function parseExportTab(value: string | null): ExportTab {
  if (value === "scalping" || value === "swing") return value;
  return "all";
}

function formatWhen(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toISOString().replace("T", " ").slice(0, 19) + " UTC";
}

function rowsForExport(signals: Signal[]): Record<string, string | number>[] {
  return signals.map((s) => ({
    Symbol: s.symbol,
    Timeframe: s.timeframe,
    Direction: s.direction.toUpperCase(),
    Entry: s.entry,
    "Stop Loss": s.stopLoss,
    "Take Profit": s.takeProfit,
    Confidence: s.confidence,
    Status: s.status === "tp_hit" ? "TP hit" : "SL hit",
    Created: formatWhen(s.createdAt),
    Closed: formatWhen(s.closedAt),
    Rationale: s.rationale,
  }));
}

export function buildClosedSignalsXlsx(signals: Signal[]): ArrayBuffer {
  const sheet = XLSX.utils.json_to_sheet(rowsForExport(signals));
  const book = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(book, sheet, "Closed signals");
  return XLSX.write(book, { type: "array", bookType: "xlsx" }) as ArrayBuffer;
}

export function buildClosedSignalsPdf(
  signals: Signal[],
  tab: ExportTab,
): ArrayBuffer {
  const doc = new jsPDF({ orientation: "landscape", unit: "pt", format: "a4" });
  const label =
    tab === "scalping"
      ? "Scalping (15m)"
      : tab === "swing"
        ? "Swing (1h)"
        : "All timeframes";

  doc.setFontSize(14);
  doc.text(`Qauntify — closed signals (${label})`, 40, 36);
  doc.setFontSize(9);
  doc.setTextColor(100);
  doc.text(`TP/SL hits only · ${signals.length} row(s)`, 40, 52);
  doc.setTextColor(0);

  autoTable(doc, {
    startY: 64,
    head: [[
      "Symbol",
      "TF",
      "Dir",
      "Entry",
      "SL",
      "TP",
      "Conf",
      "Status",
      "Created",
      "Closed",
      "Rationale",
    ]],
    body: signals.map((s) => [
      s.symbol,
      s.timeframe,
      s.direction.toUpperCase(),
      String(s.entry),
      String(s.stopLoss),
      String(s.takeProfit),
      String(s.confidence),
      s.status === "tp_hit" ? "TP hit" : "SL hit",
      formatWhen(s.createdAt),
      formatWhen(s.closedAt),
      s.rationale.slice(0, 80),
    ]),
    styles: { fontSize: 7, cellPadding: 3, overflow: "linebreak" },
    headStyles: { fillColor: [15, 23, 42], textColor: 255 },
    columnStyles: {
      10: { cellWidth: 140 },
    },
  });

  return doc.output("arraybuffer");
}

export function exportFilename(format: "xlsx" | "pdf", tab: ExportTab): string {
  const stamp = new Date().toISOString().slice(0, 10);
  return `qauntify-closed-signals-${tab}-${stamp}.${format}`;
}
