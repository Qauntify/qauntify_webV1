"use client";

import Link from "next/link";

import {
  SIGNAL_FILTER_OPTIONS,
  type SignalFilterOption,
  type SignalsBrowseTab,
} from "@/lib/signals-browse-tabs";

/** Lane selector: a segmented track of session pills rather than a plain
 * underline nav. */
export function SignalsSessionRail({
  tab,
  basePath,
  options = SIGNAL_FILTER_OPTIONS,
}: {
  tab: SignalsBrowseTab | string;
  basePath: string;
  options?: SignalFilterOption[];
}) {
  function hrefFor(id: string) {
    return id === "all" ? basePath : `${basePath}?tab=${id}`;
  }

  return (
    <nav
      aria-label="Sessions"
      className="flex w-full gap-1 overflow-x-auto rounded-xl border border-line bg-paper p-1 [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
    >
      {options.map((opt) => {
        if (opt.disabled) {
          return (
            <span
              key={opt.id}
              title="Coming soon"
              aria-disabled="true"
              className="flex shrink-0 cursor-not-allowed items-center whitespace-nowrap rounded-lg px-4 py-2.5 text-xs font-semibold text-slate opacity-40"
            >
              {opt.label}
            </span>
          );
        }
        const active = opt.id === tab;
        return (
          <Link
            key={opt.id}
            href={hrefFor(opt.id)}
            aria-current={active ? "page" : undefined}
            className={`flex shrink-0 items-center whitespace-nowrap rounded-lg px-4 py-2.5 text-xs font-semibold transition-colors ${
              active
                ? "bg-ink text-card shadow-sm"
                : "text-slate hover:bg-card hover:text-ink"
            }`}
          >
            {opt.label}
          </Link>
        );
      })}
    </nav>
  );
}
