import Link from "next/link";

import { TradeTicket } from "@/components/shared/TradeTicket";
import type { Signal } from "@/lib/signals";

const SAMPLE_SIGNAL: Signal = {
  id: "sample",
  symbol: "BTCUSDT",
  timeframe: "1h",
  direction: "long",
  entry: 108240,
  stopLoss: 106900,
  takeProfit: 110920,
  confidence: 82,
  rationale:
    "EMA crossover with positive momentum; recent ETF inflow headlines support the move.",
  indicators: { ema9: 108100, ema21: 107900, rsi: 55.2, macdHist: 12.4 },
  newsHeadlines: ["ETF inflows surge", "Bitcoin breaks resistance"],
  createdAt: new Date().toISOString(),
  status: "open",
};

export function Hero({ latestSignal }: { latestSignal: Signal | null }) {
  const signal = latestSignal ?? SAMPLE_SIGNAL;
  return (
    <section className="border-b border-line">
      <div className="mx-auto grid max-w-6xl items-center gap-12 px-6 py-20 md:grid-cols-2 md:py-28">
        <div>
          <h1 className="font-display text-5xl leading-[1.05] tracking-tight md:text-6xl">
            Smarter signals.
            <br />
            <span className="italic">Calmer</span> trading.
          </h1>
          <p className="mt-6 max-w-md text-lg leading-relaxed text-slate">
            Technical setups on crypto, gold, and forex — confirmed by AI,
            explained in plain language. Every signal ships with entry, stop
            loss, take profit, and its reasoning.
          </p>
          <div className="mt-8 flex flex-wrap items-center gap-4">
            <Link
              href="/dashboard"
              className="rounded-lg bg-ink px-5 py-3 text-sm font-medium text-paper hover:bg-ink/85"
            >
              View live signals
            </Link>
            <Link
              href="/#features"
              className="text-sm font-medium text-ink underline-offset-4 hover:underline"
            >
              How it works →
            </Link>
          </div>
        </div>
        <div>
          <TradeTicket signal={signal} sample={latestSignal === null} />
        </div>
      </div>
    </section>
  );
}
