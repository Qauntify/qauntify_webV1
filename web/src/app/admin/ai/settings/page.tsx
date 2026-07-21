import type { Metadata } from "next";

import { saveBotSettings } from "@/app/admin/actions";
import { Notice } from "@/components/shared/Notice";
import { requireAdminPage } from "@/lib/admin-guard";
import { getBotSettings, SIGNAL_STRATEGIES } from "@/lib/supabase/admin";

export const metadata: Metadata = {
  title: "Admin · AI settings — Qauntify",
};

export const revalidate = 30;

export default async function AdminAiSettings({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; saved?: string }>;
}) {
  await requireAdminPage();
  const { error, saved } = await searchParams;
  const settings = await getBotSettings();

  return (
    <div className="flex w-full flex-col gap-4">
      {error ? <Notice tone="error">{error}</Notice> : null}
      {saved ? (
        <Notice tone="success">
          AI settings saved. Changes apply on the next engine run.
        </Notice>
      ) : null}

      {settings ? (
        <form className="mt-2 flex w-full flex-col gap-8">
          <div className="grid w-full grid-cols-1 gap-6 lg:grid-cols-3">
            <section className="card-surface p-5">
              <h2 className="text-lg font-semibold">Scanning</h2>
              <p className="mt-1 text-sm text-slate">
                Pairs the engine checks every run (Kraken USD symbols).
              </p>
              <label className="mt-4 flex flex-col gap-1.5 text-sm font-medium">
                Symbols to scan
                <input
                  type="text"
                  name="symbols"
                  required
                  defaultValue={settings.symbols.join(", ")}
                  placeholder="BTCUSD, ETHUSD"
                  className="input-field w-full font-mono"
                />
                <span className="text-xs font-normal text-slate">
                  Comma-separated list, e.g. BTCUSD, ETHUSD, PAXGUSD, GBPUSD
                </span>
              </label>
            </section>

            <section className="card-surface p-5">
              <h2 className="text-lg font-semibold">Strategy</h2>
              <p className="mt-1 text-sm text-slate">
                Rules used to find candidate setups before SEA-LION confirms
                them.
              </p>
              <label className="mt-4 flex flex-col gap-1.5 text-sm font-medium">
                Signal strategy
                <select
                  name="signalStrategy"
                  defaultValue={settings.signalStrategy}
                  className="input-field w-full"
                >
                  {SIGNAL_STRATEGIES.map((strategy) => (
                    <option key={strategy.id} value={strategy.id}>
                      {strategy.label}
                    </option>
                  ))}
                </select>
                <span className="text-xs font-normal text-slate">
                  {
                    SIGNAL_STRATEGIES.find(
                      (s) => s.id === settings.signalStrategy,
                    )?.description
                  }
                </span>
              </label>
            </section>

            <section className="card-surface p-5">
              <h2 className="text-lg font-semibold">
                Quality gates
              </h2>
              <p className="mt-1 text-sm text-slate">
                Separate floors for storing confirms in the dashboard versus
                sending Telegram alerts.
              </p>
              <label className="mt-4 flex flex-col gap-1.5 text-sm font-medium">
                Min confidence to store
                <input
                  type="number"
                  name="minStoreConfidence"
                  required
                  min={0}
                  max={100}
                  step={1}
                  defaultValue={settings.minStoreConfidence}
                  className="input-field w-full max-w-[8rem]"
                />
                <span className="text-xs font-normal text-slate">
                  Confirms below this are rejected and not stored. 0 = store all
                  confirms.
                </span>
              </label>
              <label className="mt-4 flex flex-col gap-1.5 text-sm font-medium">
                Min confidence for Telegram alerts
                <input
                  type="number"
                  name="minAlertConfidence"
                  required
                  min={0}
                  max={100}
                  step={1}
                  defaultValue={settings.minAlertConfidence}
                  className="input-field w-full max-w-[8rem]"
                />
                <span className="text-xs font-normal text-slate">
                  Only stored signals at or above this get pushed to Telegram.
                </span>
              </label>
            </section>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-4 border-t border-line pt-6">
            <p className="text-sm text-slate">
              Settings apply from the next engine run (every 15 minutes).
            </p>
            <button
              formAction={saveBotSettings}
              className="btn-primary"
            >
              Save AI settings
            </button>
          </div>
        </form>
      ) : (
        <Notice tone="error">
          Could not load AI settings — run{" "}
          <code className="font-mono text-xs">supabase/schema.sql</code> in the
          Supabase SQL Editor to create the bot_settings table.
        </Notice>
      )}
    </div>
  );
}
