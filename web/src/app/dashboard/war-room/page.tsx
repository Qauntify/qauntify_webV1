import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";

import { DashboardShell } from "@/components/dashboard/DashboardShell";
import { DebateBoard } from "@/components/war-room/DebateBoard";
import { WarRoomStage } from "@/components/war-room/WarRoomStage";
import { getDebates } from "@/lib/debates";
import { createClient } from "@/lib/supabase/server";

export const metadata: Metadata = {
  title: "War Room — Qauntify",
};

export const revalidate = 20;

const TABS = [
  { id: "war-room", label: "War Room 🤖", href: "/dashboard/war-room" },
  { id: "earlier", label: "Earlier debates", href: "/dashboard/war-room?tab=earlier" },
] as const;

export default async function WarRoomPage({
  searchParams,
}: {
  searchParams: Promise<{ tab?: string }>;
}) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const { tab } = await searchParams;
  const currentTab = tab === "earlier" ? "earlier" : "war-room";

  const debates = await getDebates(12);
  const [featured, ...rest] = debates;

  return (
    <DashboardShell
      title="AI War Room"
      subtitle="Three robots debate every confirmed signal — the Manager decides"
    >
      <div className="w-full space-y-6">
        <div className="lg:hidden">
          <h1 className="text-xl font-bold">AI War Room 🤖⚔️</h1>
          <p className="text-sm text-slate">
            Three robots debate every confirmed signal — the Manager decides.
          </p>
        </div>

        <nav className="flex gap-2 border-b border-line pb-4">
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

        {currentTab === "war-room" ? (
          featured ? (
            <WarRoomStage debate={featured} />
          ) : (
            <DebateBoard debates={[]} />
          )
        ) : (
          <DebateBoard debates={rest} />
        )}

        <p className="text-xs text-slate">
          Illustration of the AI&apos;s reasoning — not financial advice.
        </p>
      </div>
    </DashboardShell>
  );
}
