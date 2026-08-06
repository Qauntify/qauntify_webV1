import type { Metadata } from "next";

import { SignalsBrowse } from "@/components/signals/SignalsBrowse";
import { Nav } from "@/components/shared/Nav";
import { parseSignalsBrowseTab } from "@/lib/signals-browse-tabs";

export const metadata: Metadata = {
  title: "Signals — Qauntify",
  description:
    "Live trading setups by session — entry, stop, targets, and outcomes.",
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
      <main className="flex min-h-[calc(100svh-4rem)] flex-1 flex-col bg-paper">
        <div className="relative overflow-hidden border-b border-line">
          <div
            className="pointer-events-none absolute inset-0 opacity-[0.45]"
            style={{
              backgroundImage:
                "linear-gradient(to right, color-mix(in srgb, var(--line) 80%, transparent) 1px, transparent 1px), linear-gradient(to bottom, color-mix(in srgb, var(--line) 80%, transparent) 1px, transparent 1px)",
              backgroundSize: "28px 28px",
              maskImage:
                "linear-gradient(to bottom, black 0%, transparent 100%)",
            }}
            aria-hidden
          />
          <div className="relative mx-auto flex w-full max-w-7xl flex-col gap-4 px-4 py-8 sm:px-6 lg:flex-row lg:items-end lg:justify-between lg:px-8 xl:px-10">
            <div className="min-w-0">
              <p className="font-mono text-[11px] font-semibold tracking-[0.2em] text-slate">
                Qauntify · SIGNAL DESK
              </p>
              <h1 className="mt-2 font-[family-name:var(--font-display)] text-3xl font-bold tracking-tight text-ink md:text-4xl">
                Signals
              </h1>
              <p className="mt-2 max-w-xl text-sm leading-relaxed text-slate">
                Pick a lane. Read entry, stop, and targets. Outcomes update as
                ticks and closes come in.
              </p>
            </div>
            <div className="flex flex-wrap gap-2 font-mono text-[11px]">
              <span className="rounded-md bg-card px-2.5 py-1.5 ring-1 ring-inset ring-line">
                AI lanes · 5M / 15M / 1H
              </span>
              <span className="rounded-md bg-card px-2.5 py-1.5 ring-1 ring-inset ring-line">
                Live EA · BBMA
              </span>
              <span className="rounded-md bg-long-soft px-2.5 py-1.5 font-semibold text-long">
                Floor · War Room
              </span>
            </div>
          </div>
        </div>

        <div className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 sm:px-6 lg:px-8 xl:px-10">
          <SignalsBrowse
            tab={currentTab}
            page={page}
            basePath="/signals"
            desk
            hideFilter
          />
        </div>
      </main>
    </>
  );
}
