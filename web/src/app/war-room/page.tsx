import type { Metadata } from "next";
import Link from "next/link";

import { Nav } from "@/components/shared/Nav";
import { DebateBoard } from "@/components/war-room/DebateBoard";
import { WarRoomStage } from "@/components/war-room/WarRoomStage";
import { getDebates } from "@/lib/debates";

export const metadata: Metadata = {
  title: "AI War Room — Qauntify",
  description:
    "Structure and Momentum robots debate every confirmed signal — the Manager decides.",
};

export const revalidate = 20;

const TABS = [
  { id: "stage", label: "Live Stage", href: "/war-room" },
  { id: "debates", label: "All Debates", href: "/war-room?tab=debates" },
] as const;

function TabNav({ current }: { current: "stage" | "debates" }) {
  return (
    <nav className="flex shrink-0 gap-2" aria-label="War Room sections">
      {TABS.map((t) => (
        <Link
          key={t.id}
          href={t.href}
          className={`rounded-md px-4 py-2 text-sm font-medium transition-colors ${
            current === t.id
              ? "bg-ink text-paper"
              : "border border-line bg-card text-slate hover:border-ink/20 hover:text-ink"
          }`}
        >
          {t.label}
        </Link>
      ))}
    </nav>
  );
}

export default async function WarRoom({
  searchParams,
}: {
  searchParams: Promise<{ tab?: string }>;
}) {
  const { tab } = await searchParams;
  const currentTab = tab === "debates" ? "debates" : "stage";
  const isStage = currentTab === "stage";

  const debates = await getDebates(24);
  const [featured, ...rest] = debates;
  const cardDebates = featured ? [featured, ...rest] : [];

  return (
    <>
      <Nav />
      {isStage ? (
        <main className="relative h-[calc(100dvh-4rem)] overflow-hidden bg-[#0b1220]">
          <div className="absolute right-3 top-3 z-30 sm:right-6">
            <TabNav current="stage" />
          </div>
          {featured ? (
            <div className="absolute inset-0">
              <WarRoomStage debate={featured} fullScreen />
            </div>
          ) : (
            <div className="flex h-full items-center justify-center px-4">
              <DebateBoard debates={[]} />
            </div>
          )}
        </main>
      ) : (
        <main className="flex h-[calc(100svh-4rem)] flex-1 flex-col overflow-hidden">
          <div className="flex shrink-0 items-center justify-between gap-4 border-b border-line px-4 py-3 sm:px-6 lg:px-8 xl:px-10">
            <div className="min-w-0">
              <p className="text-xs font-semibold uppercase tracking-wide text-accent">
                AI War Room
              </p>
              <h1 className="mt-0.5 truncate text-lg font-bold md:text-xl">
                All Debates
              </h1>
            </div>
            <TabNav current="debates" />
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto px-4 py-6 sm:px-6 lg:px-8 xl:px-10">
            <p className="mb-4 text-xs text-slate">
              Every War Room transcript on file — newest first. Illustration
              only, not financial advice.
            </p>
            <DebateBoard debates={cardDebates} />
          </div>
        </main>
      )}
    </>
  );
}
