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
  takeProfit2: null,
  takeProfit3: null,
  confidence: 82,
  rationale:
    "EMA crossover with positive momentum; recent ETF inflow headlines support the move.",
  indicators: { ema9: 108100, ema21: 107900, rsi: 55.2, macdHist: 12.4 },
  newsHeadlines: ["ETF inflows surge", "Bitcoin breaks resistance"],
  createdAt: new Date().toISOString(),
  closedAt: null,
  status: "open",
};

export function Hero({ latestSignal }: { latestSignal: Signal | null }) {
  const signal = latestSignal ?? SAMPLE_SIGNAL;
  return (
    <section className="section-block hero-mesh flex min-h-[calc(100svh-3.5rem)] items-center">
      <div className="page-container grid w-full items-center gap-12 py-10 md:grid-cols-2 md:py-12">
        <div>
          <p className="section-eyebrow">AI-confirmed signals</p>
          <h1 className="mt-3 text-4xl font-extrabold leading-tight tracking-tight md:text-5xl lg:text-6xl">
            Trade with clarity.
            <br />
            <span className="text-accent">Not guesswork.</span>
          </h1>
          <p className="mt-5 max-w-md text-base leading-relaxed text-slate md:text-lg">
            Every setup is scanned by rules, confirmed by AI, and logged with
            entry, stop loss, take profit, and a plain-language rationale.
          </p>
          <div className="mt-8 flex flex-wrap items-center gap-3">
            <Link href="/dashboard" className="btn-primary">
              Open dashboard
            </Link>
            <Link href="/signup" className="btn-secondary">
              Create free account
            </Link>
          </div>
        </div>
        <div>
          <p className="mb-3 text-xs font-medium uppercase tracking-wide text-slate">
            Latest signal
          </p>
          <TradeTicket signal={signal} sample={latestSignal === null} />
        </div>
      </div>
    </section>
  );
}
