/** Render a terminal-style setup chart from stored MT5 OHLC (SVG → PNG).
 *
 * ChartScreenShot on the VPS ignores zoom and packs hairline M1 bars.
 * Fat candles here are drawn explicitly — same black/lime look as MT5.
 */
import sharp from "sharp";

import type { Mt5CandleBar } from "@/lib/supabase/admin";

const OUT_W = 1280;
const OUT_H = 720;
const PAD_L = 16;
const PAD_R = 88;
const PAD_T = 36;
const PAD_B = 48;
const BARS = 48;

export type SetupChartSignal = {
  symbol: string;
  timeframe: string;
  direction: string;
  entry: number;
  stop_loss: number;
  take_profit: number;
  take_profit_2?: number | null;
  take_profit_3?: number | null;
  indicators?: Record<string, unknown> | null;
  created_at?: string;
};

function barMs(t: number): number {
  return t > 1e12 ? t : t * 1000;
}

function num(v: unknown): number | null {
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) && n !== 0 ? n : null;
}

function timeSec(v: unknown): number | null {
  const n = typeof v === "number" ? v : Number(v);
  if (!Number.isFinite(n) || n <= 0) return null;
  return n > 1e12 ? Math.floor(n / 1000) : Math.floor(n);
}

function pickWindow(candles: Mt5CandleBar[], anchorMs: number) {
  if (candles.length === 0) return [];
  let idx = 0;
  let best = Infinity;
  for (let i = 0; i < candles.length; i++) {
    const d = Math.abs(barMs(candles[i].open_time) - anchorMs);
    if (d < best) {
      best = d;
      idx = i;
    }
  }
  const left = Math.min(36, BARS - 12);
  const lo = Math.max(0, idx - left);
  const hi = Math.min(candles.length, lo + BARS);
  return candles.slice(Math.max(0, hi - BARS), hi);
}

function fmtPrice(p: number): string {
  if (p >= 1000) return p.toFixed(3);
  if (p >= 1) return p.toFixed(4);
  return p.toFixed(5);
}

function fmtTime(ms: number): string {
  const d = new Date(ms);
  const mon = d.toLocaleString("en-GB", { month: "short", timeZone: "UTC" });
  const day = d.getUTCDate();
  const hh = String(d.getUTCHours()).padStart(2, "0");
  const mm = String(d.getUTCMinutes()).padStart(2, "0");
  return `${day} ${mon} ${hh}:${mm}`;
}

function esc(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

export async function renderSetupChartPng(
  signal: SetupChartSignal,
  candles: Mt5CandleBar[],
): Promise<Buffer | null> {
  const ind = signal.indicators ?? {};
  const anchor =
    timeSec(ind.retest_time) ??
    timeSec(ind.fvg_end_time) ??
    timeSec(ind.choch_time) ??
    timeSec(ind.sweep_time) ??
    (signal.created_at
      ? Math.floor(new Date(signal.created_at).getTime() / 1000)
      : null);
  if (anchor == null) return null;

  const window = pickWindow(candles, anchor * 1000);
  if (window.length < 8) return null;

  const entry = signal.entry;
  const sl = signal.stop_loss;
  const tp1 = signal.take_profit;
  const tp2 = signal.take_profit_2 ?? null;
  const fvgTop = num(ind.fvg_top);
  const fvgBot = num(ind.fvg_bottom);
  const sweep = num(ind.sweep_level);
  const sweepHi = num(ind.sweep_high);
  const sweepLo = num(ind.sweep_low);
  const choch = num(ind.choch_level);

  const levels = [entry, sl, tp1, fvgTop, fvgBot, sweep, sweepHi, sweepLo, choch, tp2]
    .filter((v): v is number => v != null && v > 0);
  for (const c of window) {
    levels.push(c.high, c.low);
  }
  let ymin = Math.min(...levels);
  let ymax = Math.max(...levels);
  const span = Math.max(ymax - ymin, 1e-6);
  const pad = span * 0.12;
  ymin -= pad;
  ymax += pad;

  const plotW = OUT_W - PAD_L - PAD_R;
  const plotH = OUT_H - PAD_T - PAD_B;
  const n = window.length;
  const slot = plotW / n;
  const bodyW = Math.max(5, Math.min(16, slot * 0.62));

  const yOf = (price: number) =>
    PAD_T + ((ymax - price) / (ymax - ymin)) * plotH;
  const xOf = (i: number) => PAD_L + slot * i + slot / 2;

  const parts: string[] = [];
  parts.push(
    `<svg xmlns="http://www.w3.org/2000/svg" width="${OUT_W}" height="${OUT_H}" viewBox="0 0 ${OUT_W} ${OUT_H}">`,
  );
  parts.push(`<rect width="100%" height="100%" fill="#000000"/>`);

  // grid
  for (let g = 0; g <= 6; g++) {
    const y = PAD_T + (plotH * g) / 6;
    parts.push(
      `<line x1="${PAD_L}" y1="${y.toFixed(1)}" x2="${(OUT_W - PAD_R).toFixed(1)}" y2="${y.toFixed(1)}" stroke="#2a2a2a" stroke-width="1" stroke-dasharray="2 4"/>`,
    );
  }

  // FVG zone
  const fvgStartSec = timeSec(ind.fvg_start_time ?? ind.fvg_time);
  const fvgEndSec = timeSec(ind.fvg_end_time ?? ind.fvg_end);
  if (fvgTop != null && fvgBot != null) {
    let i0 = 0;
    let i1 = Math.min(n - 1, 3);
    if (fvgStartSec != null) {
      i0 = window.reduce(
        (best, c, i) =>
          Math.abs(barMs(c.open_time) / 1000 - fvgStartSec) <
          Math.abs(barMs(window[best].open_time) / 1000 - fvgStartSec)
            ? i
            : best,
        0,
      );
    }
    if (fvgEndSec != null) {
      i1 = window.reduce(
        (best, c, i) =>
          Math.abs(barMs(c.open_time) / 1000 - fvgEndSec) <
          Math.abs(barMs(window[best].open_time) / 1000 - fvgEndSec)
            ? i
            : best,
        i0,
      );
    }
    if (i1 < i0) [i0, i1] = [i1, i0];
    const x0 = xOf(i0) - bodyW;
    const x1 = xOf(i1) + bodyW;
    const y0 = yOf(Math.max(fvgTop, fvgBot));
    const y1 = yOf(Math.min(fvgTop, fvgBot));
    parts.push(
      `<rect x="${x0.toFixed(1)}" y="${y0.toFixed(1)}" width="${(x1 - x0).toFixed(1)}" height="${(y1 - y0).toFixed(1)}" fill="#14b8a6" fill-opacity="0.22" stroke="#14b8a6" stroke-width="1"/>`,
    );
    parts.push(
      `<text x="${(x0 + 4).toFixed(1)}" y="${(y0 - 4).toFixed(1)}" fill="#2dd4bf" font-family="Arial" font-size="13" font-weight="700">FVG</text>`,
    );
  }

  // candles — MT5-like: white bull body, hollow bear, lime wicks
  for (let i = 0; i < n; i++) {
    const c = window[i];
    const x = xOf(i);
    const yH = yOf(c.high);
    const yL = yOf(c.low);
    const yO = yOf(c.open);
    const yC = yOf(c.close);
    const up = c.close >= c.open;
    const top = Math.min(yO, yC);
    const bot = Math.max(yO, yC);
    const bh = Math.max(2, bot - top);
    parts.push(
      `<line x1="${x.toFixed(1)}" y1="${yH.toFixed(1)}" x2="${x.toFixed(1)}" y2="${yL.toFixed(1)}" stroke="#00ff00" stroke-width="1.5"/>`,
    );
    if (up) {
      parts.push(
        `<rect x="${(x - bodyW / 2).toFixed(1)}" y="${top.toFixed(1)}" width="${bodyW.toFixed(1)}" height="${bh.toFixed(1)}" fill="#ffffff" stroke="#00ff00" stroke-width="1"/>`,
      );
    } else {
      parts.push(
        `<rect x="${(x - bodyW / 2).toFixed(1)}" y="${top.toFixed(1)}" width="${bodyW.toFixed(1)}" height="${bh.toFixed(1)}" fill="#000000" stroke="#00ff00" stroke-width="1.5"/>`,
      );
    }
  }

  const hline = (
    price: number,
    color: string,
    label: string,
    dash = "6 4",
  ) => {
    const y = yOf(price);
    parts.push(
      `<line x1="${PAD_L}" y1="${y.toFixed(1)}" x2="${(OUT_W - PAD_R).toFixed(1)}" y2="${y.toFixed(1)}" stroke="${color}" stroke-width="1.6" stroke-dasharray="${dash}"/>`,
    );
    parts.push(
      `<text x="${(OUT_W - PAD_R + 6).toFixed(1)}" y="${(y + 4).toFixed(1)}" fill="${color}" font-family="Arial" font-size="12" font-weight="700">${esc(label)}</text>`,
    );
  };

  if (tp2 != null && tp2 > 0) hline(tp2, "#34d399", "TP2", "2 4");
  hline(tp1, "#34d399", "TP1");
  hline(entry, "#e2e8f0", "Entry", "0");
  if (choch != null) hline(choch, "#a78bfa", "CHoCH");
  hline(sl, "#fb7185", "SL");
  if (sweep != null) hline(sweep, "#f59e0b", "Liquidity", "0");

  // sweep / choch markers
  const markAt = (sec: number | null, price: number | null, label: string, color: string, down: boolean) => {
    if (sec == null || price == null) return;
    let bi = 0;
    let best = Infinity;
    for (let i = 0; i < n; i++) {
      const d = Math.abs(barMs(window[i].open_time) / 1000 - sec);
      if (d < best) {
        best = d;
        bi = i;
      }
    }
    const x = xOf(bi);
    const y = yOf(price);
    const dy = down ? 14 : -14;
    parts.push(
      `<polygon points="${x.toFixed(1)},${y.toFixed(1)} ${(x - 6).toFixed(1)},${(y + dy).toFixed(1)} ${(x + 6).toFixed(1)},${(y + dy).toFixed(1)}" fill="${color}"/>`,
    );
    parts.push(
      `<text x="${x.toFixed(1)}" y="${(y + dy + (down ? 12 : -4)).toFixed(1)}" fill="${color}" font-family="Arial" font-size="11" font-weight="700" text-anchor="middle">${esc(label)}</text>`,
    );
  };

  const isBuy = signal.direction === "long";
  markAt(
    timeSec(ind.sweep_time),
    isBuy ? (sweepLo ?? sweep) : (sweepHi ?? sweep),
    "Sweep",
    "#f59e0b",
    isBuy,
  );
  markAt(timeSec(ind.choch_time), choch, "CHoCH", "#a78bfa", !isBuy);

  // title + axes
  const title = `${signal.symbol.toUpperCase()}  ·  ${signal.timeframe}  ·  setup`;
  parts.push(
    `<text x="${PAD_L}" y="22" fill="#e2e8f0" font-family="Arial" font-size="14" font-weight="700">${esc(title)}</text>`,
  );

  for (let g = 0; g <= 6; g++) {
    const price = ymax - ((ymax - ymin) * g) / 6;
    const y = PAD_T + (plotH * g) / 6;
    parts.push(
      `<text x="${(OUT_W - PAD_R + 6).toFixed(1)}" y="${(y + 4).toFixed(1)}" fill="#94a3b8" font-family="Arial" font-size="11">${fmtPrice(price)}</text>`,
    );
  }

  const ticks = [0, Math.floor(n / 3), Math.floor((2 * n) / 3), n - 1];
  for (const i of ticks) {
    const x = xOf(i);
    parts.push(
      `<text x="${x.toFixed(1)}" y="${(OUT_H - 14).toFixed(1)}" fill="#94a3b8" font-family="Arial" font-size="11" text-anchor="middle">${esc(fmtTime(barMs(window[i].open_time)))}</text>`,
    );
  }

  parts.push(`</svg>`);
  const svg = Buffer.from(parts.join(""), "utf8");
  return sharp(svg).png().toBuffer();
}
