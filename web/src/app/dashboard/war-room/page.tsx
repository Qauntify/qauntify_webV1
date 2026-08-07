import type { Metadata } from "next";
import Link from "next/link";

import { DashboardShell } from "@/components/dashboard/DashboardShell";
import { DebateBoard } from "@/components/war-room/DebateBoard";
import { WarRoomStage } from "@/components/war-room/WarRoomStage";
import { getDebates } from "@/lib/debates";

export const metadata: Metadata = {
  title: "War Room — Qauntify",
};

export const revalidate = 20;

const TABS = [
  { id: "war-room", label: "Live Stage", href: "/dashboard/war-room" },
  { id: "earlier", label: "All Debates", href: "/dashboard/war-room?tab=earlier" },
] as const;

function TabNav({ current }: { current: "war-room" | "earlier" }) {
  return (
    <nav className="flex gap-2" aria-label="War Room sections">
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

export default async function WarRoomPage({
  searchParams,
}: {
  searchParams: Promise<{ tab?: string }>;
}) {
  const { tab } = await searchParams;
  const currentTab = tab === "earlier" ? "earlier" : "war-room";
  const isStage = currentTab === "war-room";

  const debates = await getDebates(12);
  const [featured, ...rest] = debates;

  return (
    <DashboardShell
      title="AI War Room"
      subtitle={
        isStage
          ? undefined
          : "Trading Floor — Structure and Momentum brief the Manager"
      }
      fullBleed={isStage}
    >
      {isStage ? (
        <div className="relative h-[calc(100dvh-4rem)] min-h-0 flex-1 overflow-hidden bg-[#0b1220]">
          <div className="absolute right-3 top-3 z-30 sm:right-6">
            <TabNav current="war-room" />
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
        </div>
      ) : (
        <div className="w-full space-y-6 p-4 lg:p-6">
          <div className="lg:hidden">
            <h1 className="text-xl font-bold">AI War Room</h1>
            <p className="text-sm text-slate">
              Trading Floor — Structure and Momentum brief the Manager.
            </p>
          </div>

          <TabNav current="earlier" />

          <DebateBoard debates={rest} />

          <p className="text-xs text-slate">
            Illustration of the AI&apos;s reasoning — not financial advice.
          </p>
        </div>
      )}
    </DashboardShell>
  );
}
