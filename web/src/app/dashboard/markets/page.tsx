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
      subtitle="Live USD candles from Kraken (no API key)."
    >
      <div className="mb-5 flex flex-col gap-4">
        <nav className="flex flex-wrap gap-2" aria-label="Market symbols">
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
        <nav className="flex flex-wrap gap-2" aria-label="Chart interval">
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

      <MarketChart symbol={symbol} interval={interval} />
    </DashboardShell>
  );
}
