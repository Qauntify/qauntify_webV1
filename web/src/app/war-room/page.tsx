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

// Debates land as the engine confirms signals — read fresh-ish.
export const revalidate = 20;

const TABS = [
  { id: "stage", label: "Live Stage", href: "/war-room" },
  { id: "debates", label: "All Debates", href: "/war-room?tab=debates" },
] as const;

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
      <main className="flex h-[calc(100svh-4rem)] flex-1 flex-col overflow-hidden">
        <div className="flex shrink-0 items-center justify-between gap-4 border-b border-line px-4 py-3 sm:px-6 lg:px-8 xl:px-10">
          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase tracking-wide text-accent">
              AI War Room
            </p>
            {!isStage ? (
              <h1 className="mt-0.5 truncate text-lg font-bold md:text-xl">
                All Debates
              </h1>
            ) : (
              <h1 className="mt-0.5 truncate text-lg font-bold md:text-xl">
                Live Stage
              </h1>
            )}
          </div>
          <nav
            className="flex shrink-0 gap-2"
            aria-label="War Room sections"
          >
            {TABS.map((t) => (
              <Link
                key={t.id}
                href={t.href}
                className={`rounded-full px-4 py-2 text-sm font-medium transition-all duration-200 ${
                  currentTab === t.id
                    ? "bg-ink text-paper shadow-md"
                    : "text-slate hover:bg-card hover:text-ink"
                }`}
              >
                {t.label}
              </Link>
            ))}
          </nav>
        </div>

        {isStage ? (
          <div className="min-h-0 flex-1">
            {featured ? (
              <WarRoomStage debate={featured} fullScreen />
            ) : (
              <div className="flex h-full items-center justify-center px-4">
                <DebateBoard debates={[]} />
              </div>
            )}
          </div>
        ) : (
          <div className="min-h-0 flex-1 overflow-y-auto px-4 py-6 sm:px-6 lg:px-8 xl:px-10">
            <p className="mb-4 text-xs text-slate">
              Every War Room transcript on file — newest first. Illustration
              only, not financial advice.
            </p>
            <DebateBoard debates={cardDebates} />
          </div>
        )}
      </main>
    </>
  );
}
