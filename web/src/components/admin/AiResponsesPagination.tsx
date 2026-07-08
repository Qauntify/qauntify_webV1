import Link from "next/link";

type AiResponsesPaginationProps = {
  page: number;
  pageSize: number;
  total: number;
  totalPages: number;
};

function pageHref(page: number): string {
  return page <= 1 ? "/admin/ai/responses" : `/admin/ai/responses?page=${page}`;
}

function visiblePages(page: number, totalPages: number): number[] {
  const start = Math.max(1, page - 2);
  const end = Math.min(totalPages, page + 2);
  const pages: number[] = [];
  for (let i = start; i <= end; i += 1) {
    pages.push(i);
  }
  return pages;
}

export function AiResponsesPagination({
  page,
  pageSize,
  total,
  totalPages,
}: AiResponsesPaginationProps) {
  if (total === 0) return null;

  const rangeStart = (page - 1) * pageSize + 1;
  const rangeEnd = Math.min(page * pageSize, total);
  const pages = visiblePages(page, totalPages);

  const linkClass =
    "rounded-lg border border-line px-3 py-1.5 text-sm font-medium text-slate transition-colors hover:border-slate hover:text-ink";
  const activeClass =
    "rounded-lg border border-accent bg-accent-soft px-3 py-1.5 text-sm font-semibold text-accent";

  return (
    <div className="mt-8 flex flex-col gap-4 border-t border-line pt-6 sm:flex-row sm:items-center sm:justify-between">
      <p className="text-sm text-slate">
        Showing {rangeStart}–{rangeEnd} of {total} responses
      </p>
      <nav
        className="flex flex-wrap items-center gap-2"
        aria-label="AI responses pagination"
      >
        {page > 1 ? (
          <Link href={pageHref(page - 1)} className={linkClass}>
            Previous
          </Link>
        ) : (
          <span className={`${linkClass} cursor-not-allowed opacity-40`}>
            Previous
          </span>
        )}

        {pages[0] > 1 ? (
          <>
            <Link href={pageHref(1)} className={linkClass}>
              1
            </Link>
            {pages[0] > 2 ? (
              <span className="px-1 text-sm text-slate">…</span>
            ) : null}
          </>
        ) : null}

        {pages.map((p) =>
          p === page ? (
            <span key={p} className={activeClass} aria-current="page">
              {p}
            </span>
          ) : (
            <Link key={p} href={pageHref(p)} className={linkClass}>
              {p}
            </Link>
          ),
        )}

        {pages[pages.length - 1] < totalPages ? (
          <>
            {pages[pages.length - 1] < totalPages - 1 ? (
              <span className="px-1 text-sm text-slate">…</span>
            ) : null}
            <Link href={pageHref(totalPages)} className={linkClass}>
              {totalPages}
            </Link>
          </>
        ) : null}

        {page < totalPages ? (
          <Link href={pageHref(page + 1)} className={linkClass}>
            Next
          </Link>
        ) : (
          <span className={`${linkClass} cursor-not-allowed opacity-40`}>
            Next
          </span>
        )}
      </nav>
    </div>
  );
}
