"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const tabs = [
  { href: "/admin", label: "Overview", exact: true },
  { href: "/admin/calendar", label: "Calendar", exact: false },
];

export function OverviewSubNav() {
  const pathname = usePathname();

  return (
    <nav
      className="mt-6 flex gap-1 border-b border-line"
      aria-label="Overview sections"
    >
      {tabs.map((tab) => {
        const active = tab.exact
          ? pathname === tab.href
          : pathname.startsWith(tab.href);
        return (
          <Link
            key={tab.href}
            href={tab.href}
            className={`-mb-px whitespace-nowrap border-b-2 px-4 py-2.5 text-sm font-medium transition-colors ${
              active
                ? "border-accent text-accent"
                : "border-transparent text-slate hover:border-line hover:text-ink"
            }`}
          >
            {tab.label}
          </Link>
        );
      })}
    </nav>
  );
}
