import type { Metadata } from "next";

import { SignalsBrowse } from "@/components/signals/SignalsBrowse";
import { Nav } from "@/components/shared/Nav";
import { parseSignalsBrowseTab } from "@/lib/signals-browse-tabs";

export const metadata: Metadata = {
  title: "Signals — Qauntify",
  description:
    "AI-confirmed trading setups with entry, stop loss, take profit, and outcomes.",
};

export const revalidate = 30;

export default async function SignalsPage({
  searchParams,
}: {
  searchParams: Promise<{ tab?: string; page?: string }>;
}) {
  const { tab, page: pageParam } = await searchParams;
  const currentTab = parseSignalsBrowseTab(tab);
  const page = Math.max(1, parseInt(pageParam ?? "1", 10) || 1);

  return (
    <>
      <Nav />
      <main className="flex min-h-[calc(100svh-4rem)] flex-1 flex-col">
        <div className="flex min-h-0 flex-1 flex-col overflow-y-auto px-4 py-6 sm:px-6 lg:px-8 xl:px-10">
          <div className="mb-5 shrink-0">
            <h1 className="text-2xl font-bold md:text-3xl">Signals</h1>
            <p className="mt-1 text-sm text-slate">
              AI-confirmed setups — refreshed every engine run
            </p>
          </div>
          <SignalsBrowse
            tab={currentTab}
            page={page}
            basePath="/signals"
          />
        </div>
      </main>
    </>
  );
}
