import type { Metadata } from "next";

import { MarketsBrowse } from "@/components/markets/MarketsBrowse";
import { Footer } from "@/components/shared/Footer";
import { Nav } from "@/components/shared/Nav";

export const metadata: Metadata = {
  title: "Markets — Qauntify",
  description: "Live USD markets — crypto/FX via Kraken, gold via COMEX.",
};

export const revalidate = 30;

export default async function MarketsPage({
  searchParams,
}: {
  searchParams: Promise<{ symbol?: string; interval?: string }>;
}) {
  const raw = await searchParams;

  return (
    <>
      <Nav />
      <main className="flex min-h-[calc(100svh-4rem)] flex-1 flex-col">
        <div className="page-container shrink-0 py-8 md:py-10">
          <h1 className="text-2xl font-bold md:text-3xl">Markets</h1>
          <p className="mt-1 text-sm text-slate">
            Live USD markets — crypto/FX via Kraken, gold via COMEX
          </p>
        </div>
        <div className="flex min-h-0 flex-1 flex-col border-t border-line">
          <MarketsBrowse
            symbolParam={raw.symbol}
            intervalParam={raw.interval}
            basePath="/markets"
          />
        </div>
      </main>
      <Footer />
    </>
  );
}
