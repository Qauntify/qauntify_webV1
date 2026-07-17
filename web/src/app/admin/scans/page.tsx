import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";

import {
  aiResponsesHrefForRun,
  countOutcomesByStatus,
  parseEngineOutcomes,
} from "@/lib/admin-scans";
import { requireAdminPage } from "@/lib/admin-guard";
import { formatDateTime } from "@/lib/format";
import { listEngineRunsPage } from "@/lib/supabase/admin";
import { Pagination } from "@/components/shared/Pagination";

export const metadata: Metadata = {
  title: "Admin · Scans — Qauntify",
};

export const revalidate = 30;

function statusClass(status: string): string {
  switch (status) {
    case "CONFIRMED":
      return "text-accent";
    case "REJECTED":
      return "text-rose-700";
    case "NO SIGNAL":
      return "text-slate";
    case "ERROR":
      return "text-rose-700";
    case "SKIPPED":
      return "text-slate/70";
    default:
      return "text-ink";
  }
}

export default async function AdminScansPage({
  searchParams,
}: {
  searchParams: Promise<{ page?: string }>;
}) {
  await requireAdminPage();
  const { page: rawPage } = await searchParams;
  const requestedPage = Number(rawPage ?? "1");
  const page =
    Number.isInteger(requestedPage) && requestedPage > 0 ? requestedPage : 1;

  const result = await listEngineRunsPage(page);
  if (!result) {
    return (
      <p className="text-sm text-slate">
        Could not load engine runs. Check Supabase configuration and that{" "}
        <code className="font-mono text-xs">engine_runs</code> exists.
      </p>
    );
  }

  if (page > result.totalPages && result.total > 0) {
    redirect(
      result.totalPages <= 1
        ? "/admin/scans"
        : `/admin/scans?page=${result.totalPages}`,
    );
  }

  const { runs, pageSize, total, totalPages } = result;

  return (
    <div className="w-full">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">Scans</h1>
          <p className="mt-1 text-sm text-slate">
            Every engine run and per-symbol outcome (confirmed, rejected, no
            signal, skipped). Open a run for details, or jump to AI responses
            for full rationales.
          </p>
        </div>
        {total > 0 ? (
          <p className="text-sm text-slate">
            Page {result.page} of {totalPages}
          </p>
        ) : null}
      </div>

      {runs.length > 0 ? (
        <>
          <div className="space-y-3">
            {runs.map((run) => {
              const outcomes = parseEngineOutcomes(run.outcomes);
              const counts = countOutcomesByStatus(outcomes);
              const summary = Object.entries(counts)
                .map(([status, n]) => `${n} ${status}`)
                .join(" · ");
              return (
                <div key={run.id} className="card-surface">
                  <div className="flex flex-wrap items-start justify-between gap-3 p-5">
                    <div>
                      <p className="font-mono text-xs text-slate">
                        {formatDateTime(run.finishedAt)}
                      </p>
                      <p className="mt-1 text-sm font-semibold">
                        Run {run.runId.slice(0, 8)} · {run.timeframe}
                      </p>
                      <p className="mt-1 text-sm text-slate">
                        Stored {run.storedCount} signal
                        {run.storedCount === 1 ? "" : "s"}
                        {summary ? ` · ${summary}` : ""}
                      </p>
                    </div>
                    <Link
                      href={aiResponsesHrefForRun(run.finishedAt)}
                      className="rounded-lg border border-line px-3 py-1.5 text-xs font-semibold text-slate hover:border-accent/40 hover:text-accent"
                    >
                      AI responses
                    </Link>
                  </div>

                  <details className="group border-t border-line">
                    <summary className="cursor-pointer list-none px-5 py-3 text-xs font-semibold text-slate marker:content-none hover:text-ink [&::-webkit-details-marker]:hidden">
                      <span className="group-open:hidden">
                        Show {outcomes.length} outcome
                        {outcomes.length === 1 ? "" : "s"}
                      </span>
                      <span className="hidden group-open:inline">
                        Hide outcomes
                      </span>
                    </summary>
                    <div className="px-5 pb-5">
                      {outcomes.length === 0 ? (
                        <p className="text-sm text-slate">
                          No per-symbol outcomes recorded for this run.
                        </p>
                      ) : (
                        <ul className="divide-y divide-line">
                          {outcomes.map((o, idx) => (
                            <li
                              key={`${run.id}-${o.symbol}-${o.timeframe ?? ""}-${o.status}-${idx}`}
                              className="flex flex-wrap items-start justify-between gap-3 py-3 first:pt-0 last:pb-0"
                            >
                              <div className="min-w-0 flex-1">
                                <p className="font-mono text-sm font-semibold">
                                  {o.symbol}
                                  {o.timeframe ? (
                                    <span className="ml-2 text-xs font-normal text-slate">
                                      {o.timeframe}
                                    </span>
                                  ) : null}
                                </p>
                                <p
                                  className={`mt-0.5 text-xs font-semibold uppercase tracking-wide ${statusClass(o.status)}`}
                                >
                                  {o.status}
                                </p>
                                {o.extra ? (
                                  <p className="mt-1 text-sm leading-relaxed text-slate">
                                    {o.extra}
                                  </p>
                                ) : null}
                              </div>
                              <Link
                                href={aiResponsesHrefForRun(run.finishedAt, {
                                  symbol: o.symbol,
                                  timeframe: o.timeframe ?? undefined,
                                })}
                                className="shrink-0 text-xs font-semibold text-accent hover:underline"
                              >
                                View AI
                              </Link>
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  </details>
                </div>
              );
            })}
          </div>

          <Pagination
            page={result.page}
            totalPages={totalPages}
            total={total}
            pageSize={pageSize}
            basePath="/admin/scans"
            itemLabel="runs"
          />
        </>
      ) : (
        <p className="mt-6 text-sm text-slate">
          No engine runs logged yet. After the next cron or manual scan, runs
          will appear here.
        </p>
      )}
    </div>
  );
}
