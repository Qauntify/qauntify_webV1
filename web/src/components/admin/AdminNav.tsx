"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const links = [
  { href: "/admin", label: "Overview" },
  { href: "/admin/signals", label: "Signals" },
  { href: "/admin/scans", label: "Scans" },
  { href: "/admin/users", label: "Users" },
  { href: "/admin/ai", label: "AI" },
];

export function AdminNav() {
  const pathname = usePathname();
  return (
    <nav className="flex gap-1 overflow-x-auto px-3 pb-3 lg:flex-col lg:pb-0">
      {links.map((l) => {
        const active =
          l.href === "/admin"
            ? pathname === "/admin" || pathname.startsWith("/admin/calendar")
            : pathname.startsWith(l.href);
        return (
          <Link
            key={l.href}
            href={l.href}
            className={`nav-item whitespace-nowrap ${active ? "nav-item-active" : ""}`}
          >
            {l.label}
          </Link>
        );
      })}
    </nav>
  );
}
