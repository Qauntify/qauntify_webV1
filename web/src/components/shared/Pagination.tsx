import Link from "next/link";

function buildHref(baseHref: string, params: Record<string, string>) {
  const url = new URL(baseHref, "http://x");
  for (const [k, v] of Object.entries(params)) {
    url.searchParams.set(k, v);
  }
  return url.pathname + "?" + url.searchParams.toString();
}

export function Pagination({
  page,
  totalPages,
  total,
  pageSize,
  basePath,
  extraParams = {},
  itemLabel = "signals",
}: {
  page: number;
  totalPages: number;
  total: number;
  pageSize: number;
  basePath: string;
  extraParams?: Record<string, string>;
  itemLabel?: string;
}) {
  if (totalPages <= 1) return null;

  const from = (page - 1) * pageSize + 1;
  const to = Math.min(page * pageSize, total);

  const hasPrev = page > 1;
  const hasNext = page < totalPages;

  // Build a compact page range: always show first, last, current ±1
  const pageSet = new Set<number>();
  pageSet.add(1);
  pageSet.add(totalPages);
  for (let p = Math.max(1, page - 1); p <= Math.min(totalPages, page + 1); p++) {
    pageSet.add(p);
  }
  const pages = Array.from(pageSet).sort((a, b) => a - b);

  return (
    <div className="mt-8 flex flex-col items-center gap-4 sm:flex-row sm:justify-between">
      <p className="text-xs text-slate font-mono">
        Showing <span className="text-ink font-semibold">{from}–{to}</span> of{" "}
        <span className="text-ink font-semibold">{total}</span> {itemLabel}
      </p>

      <nav className="flex items-center gap-1" aria-label="Pagination">
        {/* Prev */}
        {hasPrev ? (
          <Link
            href={buildHref(basePath, { ...extraParams, page: String(page - 1) })}
            className="flex items-center gap-1 rounded-lg border border-line bg-card px-3 py-1.5 text-xs font-semibold text-slate hover:border-accent/40 hover:text-accent transition-colors"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="15 18 9 12 15 6"/></svg>
            Prev
          </Link>
        ) : (
          <span className="flex items-center gap-1 rounded-lg border border-line/50 bg-card/50 px-3 py-1.5 text-xs font-semibold text-slate/40 cursor-not-allowed">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="15 18 9 12 15 6"/></svg>
            Prev
          </span>
        )}

        {/* Page numbers */}
        {pages.map((p, i) => {
          const prev = pages[i - 1];
          const showEllipsis = prev !== undefined && p - prev > 1;
          return (
            <span key={p} className="flex items-center gap-1">
              {showEllipsis && (
                <span className="px-1 text-xs text-slate/40">…</span>
              )}
              {p === page ? (
                <span className="rounded-lg border border-accent bg-accent/10 px-3 py-1.5 text-xs font-bold text-accent">
                  {p}
                </span>
              ) : (
                <Link
                  href={buildHref(basePath, { ...extraParams, page: String(p) })}
                  className="rounded-lg border border-line bg-card px-3 py-1.5 text-xs font-semibold text-slate hover:border-accent/40 hover:text-accent transition-colors"
                >
                  {p}
                </Link>
              )}
            </span>
          );
        })}

        {/* Next */}
        {hasNext ? (
          <Link
            href={buildHref(basePath, { ...extraParams, page: String(page + 1) })}
            className="flex items-center gap-1 rounded-lg border border-line bg-card px-3 py-1.5 text-xs font-semibold text-slate hover:border-accent/40 hover:text-accent transition-colors"
          >
            Next
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="9 18 15 12 9 6"/></svg>
          </Link>
        ) : (
          <span className="flex items-center gap-1 rounded-lg border border-line/50 bg-card/50 px-3 py-1.5 text-xs font-semibold text-slate/40 cursor-not-allowed">
            Next
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="9 18 15 12 9 6"/></svg>
          </span>
        )}
      </nav>
    </div>
  );
}
