"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const links = [
  { href: "/dashboard", label: "Signals", match: "signals" },
  { href: "/dashboard/war-room", label: "War Room", match: "war-room" },
  { href: "/dashboard/markets", label: "Markets", match: "markets" },
] as const;

export function DashboardNav({
  showAdmin,
}: {
  showAdmin: boolean;
}) {
  const pathname = usePathname();

  return (
    <nav className="flex flex-col gap-1 p-3">
      {links.map((l) => {
        const active =
          l.match === "signals"
            ? pathname === "/dashboard" || pathname.startsWith("/dashboard?")
            : pathname.startsWith(l.href);
        return (
          <Link
            key={l.href}
            href={l.href}
            className={`nav-item ${active ? "nav-item-active" : ""}`}
          >
            {l.match === "markets" ? (
              <CandlesIcon />
            ) : l.match === "war-room" ? (
              <RobotIcon />
            ) : (
              <ChartIcon />
            )}
            {l.label}
          </Link>
        );
      })}
      {showAdmin ? (
        <Link href="/admin" className="nav-item">
          <GearIcon />
          Admin
        </Link>
      ) : null}
    </nav>
  );
}

function ChartIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <path d="M3 3v18h18" />
      <path d="M7 16l4-8 4 5 5-9" />
    </svg>
  );
}

function RobotIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <rect x="5" y="8" width="14" height="11" rx="3" />
      <path d="M12 3v3" />
      <circle cx="12" cy="3" r="1" fill="currentColor" />
      <path d="M9 13h.01M15 13h.01" />
      <path d="M2 12v3M22 12v3" />
    </svg>
  );
}

function CandlesIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <path d="M8 4v16M16 7v13M5 9h6M13 12h6" />
    </svg>
  );
}

function GearIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <circle cx="12" cy="12" r="3" />
      <path d="M12 1v2m0 18v2M4.22 4.22l1.42 1.42m12.72 12.72 1.42 1.42M1 12h2m18 0h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42" />
    </svg>
  );
}
