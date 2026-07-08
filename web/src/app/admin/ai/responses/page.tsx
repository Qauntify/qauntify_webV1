import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { AiResponsesPagination } from "@/components/admin/AiResponsesPagination";
import { requireAdminPage } from "@/lib/admin-guard";
import { formatDateTime } from "@/lib/format";
import { listAiEventsPage } from "@/lib/supabase/admin";

export const metadata: Metadata = {
  title: "Admin · AI responses — Qauntify",
};

export const dynamic = "force-dynamic";

export default async function AdminAiResponses({
  searchParams,
}: {
  searchParams: Promise<{ page?: string }>;
}) {
  await requireAdminPage();
  const { page: rawPage } = await searchParams;
  const requestedPage = Number(rawPage ?? "1");
  const page =
    Number.isInteger(requestedPage) && requestedPage > 0 ? requestedPage : 1;

  const result = await listAiEventsPage(page);
  if (!result) {
    return (
      <p className="text-sm text-slate">
        Could not load AI responses. Check Supabase configuration.
      </p>
    );
  }

  if (page > result.totalPages && result.total > 0) {
    redirect(
      result.totalPages <= 1
        ? "/admin/ai/responses"
        : `/admin/ai/responses?page=${result.totalPages}`,
    );
  }

  const { events, pageSize, total, totalPages } = result;

  return (
    <div className="w-full">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">
            Recent responses
          </h2>
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

      {events.length > 0 ? (
        <>
          <div className="mt-6 grid w-full grid-cols-1 gap-3 xl:grid-cols-2">
            {events.map((e) => (
              <div
                key={e.id}
                className="card-surface p-5"
              >
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
          />
        </>
      ) : (
        <p className="mt-6 text-sm text-slate">
          No AI responses logged yet. Make sure you ran{" "}
          <code className="font-mono text-xs">supabase/schema.sql</code> to
          create the <code className="font-mono text-xs">ai_events</code> table,
          then run the engine once.
        </p>
      )}
    </div>
  );
}
