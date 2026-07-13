import type { Metadata } from "next";

import { DailyPnLCalendar } from "@/components/admin/DailyPnLCalendar";
import { requireAdminPage } from "@/lib/admin-guard";
import { getDailyPnLStats } from "@/lib/signals";
import { serviceRoleToken } from "@/lib/supabase/admin";

export const metadata: Metadata = {
  title: "Admin · Calendar — Qauntify",
};

export const revalidate = 30;

export default async function AdminCalendar() {
  await requireAdminPage();

  const token = serviceRoleToken();
  const pnlData = await getDailyPnLStats(token, 365);

  return <DailyPnLCalendar data={pnlData} />;
}
