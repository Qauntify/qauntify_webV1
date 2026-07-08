import Link from "next/link";

import { Logo } from "@/components/shared/Logo";

export function Footer() {
  return (
    <footer className="border-t border-line bg-card">
      <div className="page-container py-12">
        <div className="flex flex-col gap-8 md:flex-row md:justify-between">
          <div>
            <Logo />
            <p className="mt-3 max-w-sm text-sm text-slate">
              AI-confirmed trading signals with entry, stop loss, take profit,
              and outcome tracking.
            </p>
          </div>
          <nav className="flex gap-12 text-sm">
            <div className="flex flex-col gap-2">
              <p className="font-semibold text-ink">Product</p>
              <Link href="/#features" className="text-slate hover:text-accent">
                Features
              </Link>
              <Link href="/#pricing" className="text-slate hover:text-accent">
                Pricing
              </Link>
              <Link href="/dashboard" className="text-slate hover:text-accent">
                Dashboard
              </Link>
            </div>
            <div className="flex flex-col gap-2">
              <p className="font-semibold text-ink">Support</p>
              <Link href="/#faq" className="text-slate hover:text-accent">
                FAQ
              </Link>
            </div>
          </nav>
        </div>
        <p className="mt-10 border-t border-line pt-6 text-xs leading-relaxed text-slate">
          Signals are for educational and analysis purposes only. Not financial
          advice. Trading involves risk. © {new Date().getFullYear()} Qauntify.
        </p>
      </div>
    </footer>
  );
}
