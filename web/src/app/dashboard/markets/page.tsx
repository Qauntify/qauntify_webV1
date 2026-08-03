import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { DashboardShell } from "@/components/dashboard/DashboardShell";
import { MarketsBrowse } from "@/components/markets/MarketsBrowse";
import { createClient } from "@/lib/supabase/server";

export const metadata: Metadata = {
  title: "Markets — Qauntify",
};

export const revalidate = 30;

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

  return (
    <DashboardShell
      title="Markets"
      subtitle="Live USD markets — crypto/FX via Kraken, gold via COMEX"
      fullBleed
    >
      <MarketsBrowse
        symbolParam={raw.symbol}
        intervalParam={raw.interval}
        basePath="/dashboard/markets"
      />
    </DashboardShell>
  );
}
