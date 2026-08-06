"use client";

import Link from "next/link";

import {
  SIGNAL_FILTER_OPTIONS,
  type SignalFilterOption,
  type SignalsBrowseTab,
} from "@/lib/signals-browse-tabs";

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
      aria-label="Signal lanes"
      className="signals-rail flex gap-1 overflow-x-auto pb-0.5 [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
    >
      {options.map((opt) => {
        const active = opt.id === tab;
        return (
          <Link
            key={opt.id}
            href={hrefFor(opt.id)}
            aria-current={active ? "page" : undefined}
            className={`group relative flex shrink-0 flex-col rounded-md px-3.5 py-2.5 transition-colors ${
              active
                ? "bg-ink text-paper"
                : "bg-card text-ink ring-1 ring-inset ring-line hover:ring-ink/25"
            }`}
          >
            <span className="font-mono text-[11px] font-bold tracking-[0.14em]">
              {opt.code ?? opt.label.slice(0, 4).toUpperCase()}
            </span>
            <span
              className={`mt-0.5 text-[11px] font-medium ${
                active ? "text-paper/70" : "text-slate"
              }`}
            >
              {opt.label}
            </span>
            {active ? (
              <span
                className="absolute inset-x-3 -bottom-px h-0.5 rounded-full bg-long"
                aria-hidden
              />
            ) : null}
          </Link>
        );
      })}
    </nav>
  );
}
