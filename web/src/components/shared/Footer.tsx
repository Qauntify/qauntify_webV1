import Link from "next/link";

export function Footer() {
  return (
    <footer className="border-t border-line bg-ink text-paper">
      <div className="mx-auto max-w-6xl px-6 py-12">
        <div className="flex flex-col gap-8 md:flex-row md:justify-between">
          <div>
            <p className="font-display text-xl">
              Think<span className="italic">Trade</span>
            </p>
            <p className="mt-2 max-w-sm text-sm text-paper/60">
              Technical setups on BTC and ETH, confirmed by AI, explained in
              plain language.
            </p>
          </div>
          <nav className="flex gap-12 text-sm">
            <div className="flex flex-col gap-2">
              <p className="font-medium text-paper/80">Product</p>
              <Link href="/#features" className="text-paper/60 hover:text-paper">
                Features
              </Link>
              <Link href="/#pricing" className="text-paper/60 hover:text-paper">
                Pricing
              </Link>
              <Link href="/dashboard" className="text-paper/60 hover:text-paper">
                Dashboard
              </Link>
            </div>
            <div className="flex flex-col gap-2">
              <p className="font-medium text-paper/80">Company</p>
              <Link href="/#faq" className="text-paper/60 hover:text-paper">
                FAQ
              </Link>
            </div>
          </nav>
        </div>
        <p className="mt-10 border-t border-paper/15 pt-6 text-xs leading-relaxed text-paper/50">
          Signals are for educational and analysis purposes only. This is not
          financial advice. Trading involves risk and you can lose money. ©{" "}
          {new Date().getFullYear()} ThinkTrade.
        </p>
      </div>
    </footer>
  );
}
