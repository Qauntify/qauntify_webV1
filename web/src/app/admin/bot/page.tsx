import type { Metadata } from "next";

import { saveBotSettings } from "@/app/admin/actions";
import { requireAdminPage } from "@/lib/admin-guard";
import { getBotSettings } from "@/lib/supabase/admin";

export const metadata: Metadata = {
  title: "Admin · Bot settings — FinhubKH",
};

export const dynamic = "force-dynamic";

export default async function AdminBot({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; saved?: string }>;
}) {
  await requireAdminPage();
  const { error, saved } = await searchParams;
  const settings = await getBotSettings();

  return (
    <>
      <h1 className="font-display text-3xl tracking-tight">Bot settings</h1>
      <p className="mt-2 text-sm text-slate">
        Applied from the next engine run (hourly at :05). Alerts go to your
        Telegram chat.
      </p>

      {error ? (
        <p className="mt-6 max-w-xl rounded-lg bg-short-soft px-4 py-3 text-sm text-short">
          {error}
        </p>
      ) : null}
      {saved ? (
        <p className="mt-6 max-w-xl rounded-lg bg-long-soft px-4 py-3 text-sm text-long">
          Bot settings saved.
        </p>
      ) : null}

      {settings ? (
        <form className="mt-8 flex max-w-xl flex-col gap-4 rounded-xl border border-line bg-card p-5">
          <label className="flex flex-col gap-1.5 text-sm font-medium">
            Symbols to scan (comma-separated)
            <input
              type="text"
              name="symbols"
              required
              defaultValue={settings.symbols.join(", ")}
              placeholder="BTCUSDT, ETHUSDT"
              className="rounded-lg border border-line bg-paper px-3 py-2 font-mono text-sm font-normal outline-none focus:border-slate"
            />
          </label>
          <label className="flex flex-col gap-1.5 text-sm font-medium">
            Min confidence for Telegram alerts (0 = alert on everything)
            <input
              type="number"
              name="minAlertConfidence"
              required
              min={0}
              max={100}
              step={1}
              defaultValue={settings.minAlertConfidence}
              className="w-32 rounded-lg border border-line bg-paper px-3 py-2 text-sm font-normal outline-none focus:border-slate"
            />
          </label>
          <button
            formAction={saveBotSettings}
            className="self-start rounded-lg bg-ink px-4 py-2 text-sm font-medium text-paper hover:bg-ink/85"
          >
            Save settings
          </button>
        </form>
      ) : (
        <p className="mt-8 max-w-xl rounded-lg bg-short-soft px-4 py-3 text-sm text-short">
          Could not load bot settings — run{" "}
          <code className="font-mono text-xs">supabase/schema.sql</code> in the
          Supabase SQL Editor to create the bot_settings table.
        </p>
      )}
    </>
  );
}
