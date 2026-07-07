import type { Metadata } from "next";

import { saveBotSettings } from "@/app/admin/actions";
import { Notice } from "@/components/shared/Notice";
import { requireAdminPage } from "@/lib/admin-guard";
import { formatDateTime } from "@/lib/format";
import { getBotSettings, listAiEvents } from "@/lib/supabase/admin";

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
  const events = await listAiEvents(50);

  return (
    <>
      <h1 className="text-2xl font-bold">Bot settings</h1>
      <p className="mt-2 text-sm text-slate">
        Applied from the next engine run (every 10 minutes). Alerts go to
        your Telegram chat.
      </p>

      {error ? (
        <Notice tone="error" className="mt-6 max-w-xl">
          {error}
        </Notice>
      ) : null}
      {saved ? (
        <Notice tone="success" className="mt-6 max-w-xl">
          Bot settings saved.
        </Notice>
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
        <Notice tone="error" className="mt-8 max-w-xl">
          Could not load bot settings — run{" "}
          <code className="font-mono text-xs">supabase/schema.sql</code> in the
          Supabase SQL Editor to create the bot_settings table.
        </Notice>
      )}

      <h2 className="mt-12 font-display text-2xl tracking-tight">
        AI responses
      </h2>
      <p className="mt-2 max-w-3xl text-sm text-slate">
        Every SEA-LION response the engine produced: confirms, rejects, and
        no-signal explanations (newest first).
      </p>
      {events && events.length > 0 ? (
        <div className="mt-6 flex max-w-4xl flex-col gap-3">
          {events.map((e) => (
            <div
              key={e.id}
              className="rounded-xl border border-line bg-card p-5"
            >
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
                <span className="font-mono text-xs text-slate">
                  {formatDateTime(e.createdAt)}
                </span>
                <span className="font-display text-base">
                  {e.kind === "confirm"
                    ? "CONFIRM"
                    : e.kind === "reject"
                      ? "REJECT"
                      : "NO SETUP"}
                </span>
                <span className="rounded bg-line px-2 py-0.5 font-mono text-xs">
                  {e.symbol} · {e.timeframe}
                </span>
                {e.direction ? (
                  <span className="rounded bg-line px-2 py-0.5 font-mono text-xs">
                    {e.direction.toUpperCase()}
                  </span>
                ) : null}
                {typeof e.confidence === "number" ? (
                  <span className="rounded bg-line px-2 py-0.5 font-mono text-xs">
                    {e.confidence}%
                  </span>
                ) : null}
              </div>

              {e.entry != null && e.stopLoss != null && e.takeProfit != null ? (
                <p className="mt-3 font-mono text-xs text-slate">
                  Entry {e.entry} | SL {e.stopLoss} | TP {e.takeProfit}
                </p>
              ) : null}

              <p className="mt-3 whitespace-pre-wrap text-sm leading-relaxed">
                {e.rationale}
              </p>

              <details className="mt-4">
                <summary className="cursor-pointer text-sm text-slate hover:text-ink">
                  Show raw context (indicators + headlines)
                </summary>
                <pre className="mt-3 overflow-auto rounded-lg border border-line bg-paper p-3 text-xs text-slate">
                  {JSON.stringify(
                    {
                      indicators: e.indicators,
                      newsHeadlines: e.newsHeadlines,
                    },
                    null,
                    2,
                  )}
                </pre>
              </details>
            </div>
          ))}
        </div>
      ) : (
        <p className="mt-6 text-sm text-slate">
          No AI responses logged yet. Make sure you ran{" "}
          <code className="font-mono text-xs">supabase/schema.sql</code> to
          create the <code className="font-mono text-xs">ai_events</code> table,
          then run the engine once.
        </p>
      )}
    </>
  );
}
