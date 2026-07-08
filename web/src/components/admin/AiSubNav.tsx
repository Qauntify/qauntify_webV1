"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const tabs = [
  { href: "/admin/ai/settings", label: "AI settings" },
  { href: "/admin/ai/responses", label: "AI responses" },
];

export function AiSubNav() {
  const pathname = usePathname();

  return (
    <nav
      className="mt-6 flex gap-1 border-b border-line"
      aria-label="AI sections"
    >
      {tabs.map((tab) => {
        const active = pathname.startsWith(tab.href);
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
