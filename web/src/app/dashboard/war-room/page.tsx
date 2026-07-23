import type { Metadata } from "next";
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

export default async function WarRoomPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const debates = await getDebates(8);
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

        {featured ? (
          <>
            <WarRoomStage debate={featured} />
            {rest.length > 0 ? (
              <>
                <h3 className="mb-3 mt-2 text-sm font-semibold text-ink">
                  Earlier debates
                </h3>
                <DebateBoard debates={rest} />
              </>
            ) : null}
          </>
        ) : (
          <DebateBoard debates={[]} />
        )}

        <p className="text-xs text-slate">
          Illustration of the AI&apos;s reasoning — not financial advice.
        </p>
      </div>
    </DashboardShell>
  );
}
