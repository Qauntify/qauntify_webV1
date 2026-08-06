import { redirect } from "next/navigation";

import { DashboardShell } from "@/components/dashboard/DashboardShell";
import { SignalsBrowse } from "@/components/signals/SignalsBrowse";
import { SignalsBrowseFilter } from "@/components/signals/SignalsBrowseFilter";
import { Notice } from "@/components/shared/Notice";
import { parseSignalsBrowseTab } from "@/lib/signals-browse-tabs";
import { createClient } from "@/lib/supabase/server";

export const metadata = {
  title: "Dashboard — Qauntify",
};

export const revalidate = 30;

export default async function Dashboard({
  searchParams,
}: {
  searchParams: Promise<{ admin?: string; tab?: string; page?: string }>;
}) {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");
  const { data: { session } } = await supabase.auth.getSession();
  const accessToken = session?.access_token;
  const { admin, tab, page: pageParam } = await searchParams;

  const currentTab = parseSignalsBrowseTab(tab);
  const page = Math.max(1, parseInt(pageParam ?? "1", 10) || 1);

  return (
    <DashboardShell
      title="Signals"
      subtitle="AI-confirmed setups — refreshed every engine run"
      actions={
        <SignalsBrowseFilter
          tab={currentTab}
          basePath="/dashboard"
          showLabel={false}
          compact
        />
      }
    >
      <div className="w-full space-y-6">
        {admin === "denied" ? (
          <Notice tone="error">
            Admin access is not enabled for {user.email}. Ask the
            owner to add your email to ADMIN_EMAILS, then sign out and back in.
          </Notice>
        ) : null}

        <div className="flex flex-wrap items-center justify-between gap-4 lg:hidden">
          <div className="min-w-0">
            <h1 className="text-xl font-bold">Signals</h1>
            <p className="text-sm text-slate">
              AI-confirmed setups — refreshed every engine run
            </p>
          </div>
          <SignalsBrowseFilter
            tab={currentTab}
            basePath="/dashboard"
            showLabel={false}
            compact
          />
        </div>

        <SignalsBrowse
          tab={currentTab}
          page={page}
          accessToken={accessToken}
          basePath="/dashboard"
          hideFilter
        />
      </div>
    </DashboardShell>
  );
}
