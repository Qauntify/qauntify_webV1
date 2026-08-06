"use client";

import Link from "next/link";

import {
  SIGNAL_FILTER_OPTIONS,
  type SignalFilterOption,
  type SignalsBrowseTab,
} from "@/lib/signals-browse-tabs";

/** Clean underline session tabs. */
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
      className="flex gap-1 overflow-x-auto border-b border-line [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
    >
      {options.map((opt) => {
        const active = opt.id === tab;
        return (
          <Link
            key={opt.id}
            href={hrefFor(opt.id)}
            aria-current={active ? "page" : undefined}
            className={`relative shrink-0 whitespace-nowrap px-4 py-3 text-sm font-medium transition-colors ${
              active
                ? "text-ink"
                : "text-slate hover:text-ink"
            }`}
          >
            {opt.label}
            {active ? (
              <span
                className="absolute inset-x-2 -bottom-px h-0.5 rounded-full bg-ink"
                aria-hidden
              />
            ) : null}
          </Link>
        );
      })}
    </nav>
  );
}
