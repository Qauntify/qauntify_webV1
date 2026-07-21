"use client";

import { useEffect, useRef, useState } from "react";
import {
  ColorType,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type CandlestickData,
  type Time,
} from "lightweight-charts";

import type { MarketCandle, MarketInterval } from "@/lib/markets/kraken";

type MarketChartProps = {
  symbol: string;
  interval: MarketInterval;
};

export function MarketChart({ symbol, interval }: MarketChartProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [lastClose, setLastClose] = useState<number | null>(null);
  const [candleCount, setCandleCount] = useState(0);

  // Recreate the chart whenever the market changes so the price scale is
  // never stuck on a previous symbol's range (BTC → GBP looked blank).
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const chart = createChart(el, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "#64748b",
      },
      grid: {
        vertLines: { color: "rgba(148, 163, 184, 0.12)" },
        horzLines: { color: "rgba(148, 163, 184, 0.12)" },
      },
      rightPriceScale: {
        borderVisible: false,
        autoScale: true,
      },
      timeScale: { borderVisible: false, timeVisible: true },
      crosshair: { mode: 1 },
    });
    const series = chart.addCandlestickSeries({
      upColor: "#0f766e",
      downColor: "#be123c",
      borderVisible: false,
      wickUpColor: "#0f766e",
      wickDownColor: "#be123c",
      priceFormat: {
        type: "price",
        precision: symbol === "GBPUSD" ? 5 : 2,
        minMove: symbol === "GBPUSD" ? 0.00001 : 0.01,
      },
    });
    chartRef.current = chart;
    seriesRef.current = series;

    let cancelled = false;
    setLoading(true);
    setError(null);
    setLastClose(null);
    setCandleCount(0);

    async function load() {
      try {
        const response = await fetch(
          `/api/markets/candles?symbol=${encodeURIComponent(symbol)}&interval=${interval}`,
          { cache: "no-store" },
        );
        const body = (await response.json()) as {
          candles?: MarketCandle[];
          error?: string;
        };
        if (!response.ok) {
          throw new Error(body.error || `HTTP ${response.status}`);
        }
        const candles = body.candles ?? [];
        const data: CandlestickData<Time>[] = candles.map((c) => ({
          time: c.time as Time,
          open: c.open,
          high: c.high,
          low: c.low,
          close: c.close,
        }));
        if (cancelled) return;
        if (!seriesRef.current || !chartRef.current) return;
        if (data.length === 0) {
          setError("No candles returned for this market");
          setCandleCount(0);
          setLastClose(null);
          return;
        }
        seriesRef.current.setData(data);
        chartRef.current.priceScale("right").applyOptions({ autoScale: true });
        chartRef.current.timeScale().fitContent();
        setCandleCount(data.length);
        setLastClose(data[data.length - 1].close);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load chart");
          setLastClose(null);
          setCandleCount(0);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void load();

    return () => {
      cancelled = true;
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, [symbol, interval]);

  return (
    <div className="flex h-full min-h-0 flex-col bg-paper">
      <div className="flex shrink-0 flex-wrap items-end justify-between gap-3 border-b border-line px-4 py-3 lg:px-6">
        <div>
          <p className="font-mono text-xs uppercase tracking-wide text-slate">
            {symbol} · {interval} · USD
            {symbol === "XAUUSD" ? " · COMEX gold" : ""}
          </p>
          <p className="mt-1 font-mono text-2xl font-semibold tabular-nums">
            {lastClose != null
              ? lastClose.toLocaleString(undefined, {
                  maximumFractionDigits:
                    symbol === "GBPUSD" ? 5 : lastClose >= 100 ? 2 : 4,
                })
              : "—"}
          </p>
        </div>
        {loading ? (
          <p className="text-xs text-slate">Loading candles…</p>
        ) : error ? (
          <p className="text-xs text-rose-700">{error}</p>
        ) : (
          <p className="text-xs text-slate">
            {candleCount} candles · {symbol === "XAUUSD" ? "Yahoo GC=F" : "Kraken"}
          </p>
        )}
      </div>
      <div ref={containerRef} className="min-h-0 w-full flex-1" />
    </div>
  );
}
