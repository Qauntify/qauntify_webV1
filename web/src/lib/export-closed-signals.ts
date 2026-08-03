import ExcelJS from "exceljs";
import { jsPDF } from "jspdf";
import autoTable from "jspdf-autotable";

import type { Signal } from "@/lib/signals";

export type ExportTab = "all" | "super-scalping" | "scalping" | "swing";

export function timeframeForTab(tab: ExportTab): string | undefined {
  if (tab === "super-scalping") return "5m";
  if (tab === "scalping") return "15m";
  if (tab === "swing") return "1h";
  return undefined;
}

export function parseExportTab(value: string | null): ExportTab {
  if (value === "super-scalping" || value === "scalping" || value === "swing") {
    return value;
  }
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
    "Take Profit 2": s.takeProfit2 ?? "",
    "Take Profit 3": s.takeProfit3 ?? "",
    Confidence: s.confidence,
    Status: s.status === "sl_hit"
      ? "SL hit"
      : s.status === "tp3_hit"
        ? "TP3 hit"
        : s.status === "tp2_hit"
          ? "TP2 hit"
          : s.status === "tp1_hit"
            ? "TP1 hit"
            : "TP hit",
    Created: formatWhen(s.createdAt),
    Closed: formatWhen(s.closedAt),
    Rationale: s.rationale,
  }));
}

/**
 * Async because ExcelJS streams the workbook out. It replaced the `xlsx`
 * package, which has unpatched prototype-pollution and ReDoS advisories with
 * "no fix available" — npm's published build is unmaintained.
 */
export async function buildClosedSignalsXlsx(signals: Signal[]): Promise<ArrayBuffer> {
  const rows = rowsForExport(signals);
  const book = new ExcelJS.Workbook();
  const sheet = book.addWorksheet("Closed signals");
  const headers = Object.keys(rows[0] ?? {});
  sheet.columns = headers.map((header) => ({
    header,
    key: header,
    // Rationale is a paragraph; everything else is short.
    width: header === "Rationale" ? 80 : Math.max(12, header.length + 2),
  }));
  sheet.getRow(1).font = { bold: true };
  for (const row of rows) sheet.addRow(row);
  return book.xlsx.writeBuffer() as Promise<ArrayBuffer>;
}

export function buildClosedSignalsPdf(
  signals: Signal[],
  tab: ExportTab,
): ArrayBuffer {
  const doc = new jsPDF({ orientation: "landscape", unit: "pt", format: "a4" });
  const label =
    tab === "super-scalping"
      ? "Super scalping (5m)"
      : tab === "scalping"
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
      String(s.takeProfit2 ?? ""),
      String(s.takeProfit3 ?? ""),
      String(s.confidence),
      s.status === "sl_hit"
        ? "SL hit"
        : s.status === "tp3_hit"
          ? "TP3 hit"
          : s.status === "tp2_hit"
            ? "TP2 hit"
            : s.status === "tp1_hit"
              ? "TP1 hit"
              : "TP hit",
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
