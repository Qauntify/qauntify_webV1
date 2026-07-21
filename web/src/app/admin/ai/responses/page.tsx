import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";

import { AiResponsesPagination } from "@/components/admin/AiResponsesPagination";
import {
  aiResponsesHref,
  parseAiEventFilters,
  type AiEventFilters,
} from "@/lib/admin-ai-filters";
import { requireAdminPage } from "@/lib/admin-guard";
import { formatDateTime } from "@/lib/format";
import { listAiEventsPage } from "@/lib/supabase/admin";

export const metadata: Metadata = {
  title: "Admin · AI responses — Qauntify",
};

export const revalidate = 30;

function filterLink(
  filters: AiEventFilters,
  patch: Partial<AiEventFilters> | "clear-kind" | "clear-timeframe",
  label: string,
  active: boolean,
) {
  let next: AiEventFilters = { ...filters };
  if (patch === "clear-kind") {
    delete next.kind;
  } else if (patch === "clear-timeframe") {
    delete next.timeframe;
  } else {
    next = { ...next, ...patch };
  }
  // Changing filters resets to page 1 via href without page.
  const href = aiResponsesHref(next, 1);
  return (
    <Link
      href={href}
      className={`nav-item ${active ? "nav-item-active" : ""}`}
    >
      {label}
    </Link>
  );
}

export default async function AdminAiResponses({
  searchParams,
}: {
  searchParams: Promise<{
    page?: string;
    symbol?: string;
    timeframe?: string;
    kind?: string;
    since?: string;
    until?: string;
  }>;
}) {
  await requireAdminPage();
  const raw = await searchParams;
  const filters = parseAiEventFilters(raw);
  const requestedPage = Number(raw.page ?? "1");
  const page =
    Number.isInteger(requestedPage) && requestedPage > 0 ? requestedPage : 1;

  const result = await listAiEventsPage(page, undefined, filters);
  if (!result) {
    return (
      <p className="text-sm text-slate">
        Could not load AI responses. Check Supabase configuration.
      </p>
    );
  }

  if (page > result.totalPages && result.total > 0) {
    redirect(aiResponsesHref(filters, result.totalPages));
  }

  const { events, pageSize, total, totalPages } = result;
  const hasFilters = Boolean(
    filters.symbol ||
      filters.timeframe ||
      filters.kind ||
      filters.since ||
      filters.until,
  );

  return (
    <div className="w-full">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">Recent responses</h2>
          <p className="mt-1 text-sm text-slate">
            Every SEA-LION reply from the engine: confirms, rejects, and
            no-setup explanations (newest first).
          </p>
        </div>
        {total > 0 ? (
          <p className="text-sm text-slate">
            Page {result.page} of {totalPages}
          </p>
        ) : null}
      </div>

      <div className="mt-6 space-y-4 border-b border-line pb-5">
        <div>
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate">
            Kind
          </p>
          <nav className="flex flex-wrap gap-2">
            {filterLink(filters, "clear-kind", "All", !filters.kind)}
            {filterLink(
              filters,
              { kind: "confirm" },
              "Confirm",
              filters.kind === "confirm",
            )}
            {filterLink(
              filters,
              { kind: "reject" },
              "Reject",
              filters.kind === "reject",
            )}
            {filterLink(
              filters,
              { kind: "no_setup" },
              "No setup",
              filters.kind === "no_setup",
            )}
          </nav>
        </div>

        <div>
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate">
            Timeframe
          </p>
          <nav className="flex flex-wrap gap-2">
            {filterLink(filters, "clear-timeframe", "All", !filters.timeframe)}
            {filterLink(
              filters,
              { timeframe: "5m" },
              "Super scalp (5m)",
              filters.timeframe === "5m",
            )}
            {filterLink(
              filters,
              { timeframe: "15m" },
              "Scalping (15m)",
              filters.timeframe === "15m",
            )}
            {filterLink(
              filters,
              { timeframe: "1h" },
              "Swing (1h)",
              filters.timeframe === "1h",
            )}
          </nav>
        </div>

        <form method="get" className="flex flex-wrap items-end gap-3">
          {filters.kind ? (
            <input type="hidden" name="kind" value={filters.kind} />
          ) : null}
          {filters.timeframe ? (
            <input type="hidden" name="timeframe" value={filters.timeframe} />
          ) : null}
          {filters.since ? (
            <input type="hidden" name="since" value={filters.since} />
          ) : null}
          {filters.until ? (
            <input type="hidden" name="until" value={filters.until} />
          ) : null}
          <label className="block text-sm">
            <span className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate">
              Symbol
            </span>
            <input
              name="symbol"
              defaultValue={filters.symbol ?? ""}
              placeholder="e.g. BTCUSD"
              className="w-44 rounded-lg border border-line bg-card px-3 py-1.5 font-mono text-sm"
            />
          </label>
          <button
            type="submit"
            className="rounded-lg border border-line px-3 py-1.5 text-sm font-semibold text-slate hover:border-accent/40 hover:text-accent"
          >
            Apply
          </button>
          {hasFilters ? (
            <Link
              href="/admin/ai/responses"
              className="rounded-lg px-3 py-1.5 text-sm font-semibold text-slate hover:text-accent"
            >
              Clear filters
            </Link>
          ) : null}
        </form>

        {filters.since || filters.until ? (
          <p className="font-mono text-xs text-slate">
            Time window
            {filters.since ? ` from ${formatDateTime(filters.since)}` : ""}
            {filters.until ? ` to ${formatDateTime(filters.until)}` : ""}
          </p>
        ) : null}
      </div>

      {events.length > 0 ? (
        <>
          <div className="mt-6 grid w-full grid-cols-1 gap-3 xl:grid-cols-2">
            {events.map((e) => (
              <div key={e.id} className="card-surface p-5">
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
                  <span className="font-mono text-xs text-slate">
                    {formatDateTime(e.createdAt)}
                  </span>
                  <span className="font-mono text-sm font-semibold uppercase tracking-wide">
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

                {e.entry != null &&
                e.stopLoss != null &&
                e.takeProfit != null ? (
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

          <AiResponsesPagination
            page={result.page}
            pageSize={pageSize}
            total={total}
            totalPages={totalPages}
            filters={filters}
          />
        </>
      ) : (
        <p className="mt-6 text-sm text-slate">
          {hasFilters
            ? "No AI responses match these filters."
            : (
              <>
                No AI responses logged yet. Make sure you ran{" "}
                <code className="font-mono text-xs">supabase/schema.sql</code>{" "}
                to create the{" "}
                <code className="font-mono text-xs">ai_events</code> table, then
                run the engine once.
              </>
            )}
        </p>
      )}
    </div>
  );
}
