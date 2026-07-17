import type { Metadata } from "next";

import { TradingFloor } from "@/components/floor/TradingFloor";
import { requireAdminPage } from "@/lib/admin-guard";

export const metadata: Metadata = {
  title: "Admin · Trading Floor — Qauntify",
};

export default async function AdminTradingFloorPage() {
  await requireAdminPage();

  return (
    <div className="flex w-full flex-col gap-4">
      <div>
        <h1 className="text-2xl font-bold">Gold Trading Floor</h1>
        <p className="mt-1 text-sm text-slate">
          AI gold hunter — four desks plus PM signal/pass. Runs until you stop.
        </p>
      </div>
      <TradingFloor />
    </div>
  );
}
