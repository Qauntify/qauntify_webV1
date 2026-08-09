import type { Metadata } from "next";

import { SignalsBrowse } from "@/components/signals/SignalsBrowse";
import { Nav } from "@/components/shared/Nav";
import {
  parseAiSignalStrategy,
  parseSignalsBrowseTab,
} from "@/lib/signals-browse-tabs";

export const metadata: Metadata = {
  title: "Signals — Qauntify",
  description:
    "ការរៀបចំជួញដូរផ្ទាល់តាមវគ្គ — ចូល បញ្ឈប់ គោលដៅ និងលទ្ធផល។",
};

export const revalidate = 30;

export default async function SignalsPage({
  searchParams,
}: {
  searchParams: Promise<{ tab?: string; strategy?: string; page?: string }>;
}) {
  const { tab, strategy, page: pageParam } = await searchParams;
  const currentTab = parseSignalsBrowseTab(tab);
  const currentStrategy = parseAiSignalStrategy(strategy);
  const page = Math.max(1, parseInt(pageParam ?? "1", 10) || 1);

  return (
    <>
      <Nav />
      <main className="flex min-h-[calc(100svh-4rem)] flex-1 flex-col bg-paper">
        <div className="w-full flex-1 px-4 py-8 sm:px-6 lg:px-8 xl:px-10">
          <div className="mb-8">
            <h1 className="text-3xl font-bold tracking-tight text-ink md:text-4xl">
              Signals
            </h1>
            <p className="mt-2 max-w-2xl text-base text-slate">
              ការរៀបចំដែល AI បញ្ជាក់ និង EA ផ្ទាល់ — ចូល បញ្ឈប់ គោលដៅ និងលទ្ធផល។
            </p>
          </div>

          <SignalsBrowse
            tab={currentTab}
            strategy={currentStrategy}
            page={page}
            basePath="/signals"
            hideFilter
          />
        </div>
      </main>
    </>
  );
}
