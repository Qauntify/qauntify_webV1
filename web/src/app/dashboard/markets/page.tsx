import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";

import { DashboardShell } from "@/components/dashboard/DashboardShell";
import { MarketChart } from "@/components/markets/MarketChart";
import {
  DEFAULT_MARKET_SYMBOLS,
  canonicalMarketSymbol,
  parseMarketInterval,
} from "@/lib/markets/kraken";
import { createClient } from "@/lib/supabase/server";

export const metadata: Metadata = {
  title: "Markets — Qauntify",
};

export const revalidate = 30;

const INTERVALS = [
  { id: "5m", label: "5m" },
  { id: "15m", label: "15m" },
  { id: "1h", label: "1h" },
] as const;

export default async function MarketsPage({
  searchParams,
}: {
  searchParams: Promise<{ symbol?: string; interval?: string }>;
}) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const raw = await searchParams;
  const requested = canonicalMarketSymbol(raw.symbol ?? "BTCUSD");
  const symbol = (DEFAULT_MARKET_SYMBOLS as readonly string[]).includes(requested)
    ? requested
    : "BTCUSD";
  const interval = parseMarketInterval(raw.interval);

  return (
    <DashboardShell
      title="Markets"
      subtitle="Live USD markets — crypto/FX via Kraken, gold via COMEX"
      fullBleed
    >
      <div className="flex min-h-0 flex-1 flex-col">
        <div className="flex shrink-0 flex-wrap items-center gap-3 border-b border-line bg-card/60 px-4 py-3 lg:px-6">
          <nav className="flex flex-wrap gap-1.5" aria-label="Market symbols">
            {DEFAULT_MARKET_SYMBOLS.map((s) => (
              <Link
                key={s}
                href={`/dashboard/markets?symbol=${s}&interval=${interval}`}
                className={`nav-item ${s === symbol ? "nav-item-active" : ""}`}
              >
                {s}
              </Link>
            ))}
          </nav>
          <span className="hidden h-5 w-px bg-line sm:block" aria-hidden />
          <nav className="flex flex-wrap gap-1.5" aria-label="Chart interval">
            {INTERVALS.map((i) => (
              <Link
                key={i.id}
                href={`/dashboard/markets?symbol=${symbol}&interval=${i.id}`}
                className={`nav-item ${i.id === interval ? "nav-item-active" : ""}`}
              >
                {i.label}
              </Link>
            ))}
          </nav>
        </div>

        <div className="min-h-0 flex-1">
          <MarketChart
            key={`${symbol}-${interval}`}
            symbol={symbol}
            interval={interval}
          />
        </div>
      </div>
    </DashboardShell>
  );
}
