import type { Metadata } from "next";

import { requireAdminPage } from "@/lib/admin-guard";
import { formatDateTime } from "@/lib/format";
import { listCronStatuses, type WorkflowRunSummary } from "@/lib/github-engine";
import { getXauScanStatus } from "@/lib/supabase/admin";

export const metadata: Metadata = {
  title: "Admin · Cron — Qauntify",
};

export const dynamic = "force-dynamic";

function runTone(run: WorkflowRunSummary): string {
  if (run.status === "in_progress" || run.status === "queued") {
    return "text-amber-700";
  }
  switch (run.conclusion) {
    case "success":
      return "text-accent";
    case "failure":
    case "timed_out":
    case "startup_failure":
      return "text-rose-700";
    case "cancelled":
      return "text-slate/70";
    default:
      return "text-ink";
  }
}

function runLabel(run: WorkflowRunSummary): string {
  if (run.status === "in_progress") return "running";
  if (run.status === "queued") return "queued";
  return run.conclusion ?? run.status ?? "unknown";
}

export default async function AdminCronPage() {
  await requireAdminPage();

  const [statuses, xau] = await Promise.all([
    listCronStatuses(8),
    getXauScanStatus(),
  ]);

  const alertsConfigured = Boolean(
    process.env.TELEGRAM_BOT_TOKEN?.trim() &&
      process.env.TELEGRAM_ALERTS_CHAT_ID?.trim(),
  );

  return (
    <div className="w-full">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">Cron</h1>
          <p className="mt-1 max-w-2xl text-sm text-slate">
            Latest GitHub Actions runs for each cron-job.org → Vercel → workflow
            path. Failures also ping the ops Telegram channel (
            <code className="font-mono text-xs">TELEGRAM_ALERTS_CHAT_ID</code>).
          </p>
        </div>
        <p
          className={`text-xs font-medium ${alertsConfigured ? "text-accent" : "text-rose-700"}`}
        >
          {alertsConfigured
            ? "Ops Telegram alerts on"
            : "Ops Telegram alerts off — set TELEGRAM_ALERTS_CHAT_ID"}
        </p>
      </div>

      <section className="mb-8 border border-line bg-paper p-4">
        <h2 className="text-sm font-semibold text-ink">XAU watchdog</h2>
        <p className="mt-1 text-xs text-slate">
          Heartbeat from the 1m scalper. Stale →{" "}
          <code className="font-mono">/api/cron/xau-watchdog</code> restarts
          the workflow.
        </p>
        {xau ? (
          <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-3">
            <div>
              <dt className="text-xs text-slate">Status</dt>
              <dd className={xau.isHealthy ? "text-accent" : "text-rose-700"}>
                {xau.isHealthy ? "healthy" : "stale"}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-slate">Age</dt>
              <dd className="font-mono text-ink">
                {xau.ageMinutes != null ? `${xau.ageMinutes.toFixed(1)}m` : "—"}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-slate">Last scan</dt>
              <dd className="font-mono text-ink">
                {xau.finishedAt ? formatDateTime(xau.finishedAt) : "—"}
              </dd>
            </div>
          </dl>
        ) : (
          <p className="mt-3 text-sm text-slate">No XAU scan status yet.</p>
        )}
      </section>

      <div className="grid gap-6 lg:grid-cols-2">
        {statuses.map((wf) => {
          const latest = wf.runs[0];
          return (
            <section
              key={wf.key}
              className="border border-line bg-paper p-4"
            >
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <h2 className="text-sm font-semibold text-ink">{wf.label}</h2>
                {latest ? (
                  <span className={`text-xs font-medium ${runTone(latest)}`}>
                    {runLabel(latest)}
                  </span>
                ) : null}
              </div>
              <p className="mt-1 font-mono text-[11px] text-slate">
                {wf.trigger} · {wf.file}
              </p>

              {wf.error ? (
                <p className="mt-3 text-sm text-rose-700">{wf.error}</p>
              ) : wf.runs.length === 0 ? (
                <p className="mt-3 text-sm text-slate">No runs yet.</p>
              ) : (
                <ul className="mt-3 divide-y divide-line">
                  {wf.runs.map((run) => (
                    <li
                      key={run.id}
                      className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm"
                    >
                      <div>
                        <a
                          href={run.html_url}
                          target="_blank"
                          rel="noreferrer"
                          className="font-medium text-ink underline-offset-2 hover:underline"
                        >
                          #{run.run_number}
                        </a>
                        <span className="ml-2 text-xs text-slate">
                          {run.event}
                        </span>
                      </div>
                      <div className="flex items-center gap-3 text-xs">
                        <span className={runTone(run)}>{runLabel(run)}</span>
                        <time
                          className="font-mono text-slate"
                          dateTime={run.created_at}
                        >
                          {formatDateTime(run.created_at)}
                        </time>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          );
        })}
      </div>
    </div>
  );
}
