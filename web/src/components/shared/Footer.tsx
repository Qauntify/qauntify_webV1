import Link from "next/link";

import { Logo } from "@/components/shared/Logo";

export function Footer() {
  return (
    <footer className="border-t border-line bg-card">
      <div className="page-container py-5">
        <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
          <div>
            <Logo />
            <p className="mt-1.5 max-w-sm text-sm text-slate">
              AI-confirmed trading signals with entry, stop, targets, and
              outcome tracking. Free for every trader — no account, no
              paywall.
            </p>
          </div>
          <nav className="flex flex-wrap gap-x-5 gap-y-1 text-sm">
            <Link href="/signals" className="font-medium text-slate hover:text-ink">
              Signals
            </Link>
            <Link href="/war-room" className="font-medium text-slate hover:text-ink">
              War Room
            </Link>
            <Link href="/track-record" className="font-medium text-slate hover:text-ink">
              Track Record
            </Link>
          </nav>
        </div>
        <p className="mt-4 border-t border-line pt-3 text-xs leading-relaxed text-slate">
          Signals are for educational and analysis purposes only. Not financial
          advice. Trading involves risk. © {new Date().getFullYear()} Qauntify.
        </p>
      </div>
    </footer>
  );
}
