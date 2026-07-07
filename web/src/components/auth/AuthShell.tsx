import Link from "next/link";

// Split-screen frame for the auth pages: ink brand panel with a sample
// journal entry on the left, form on the right. No Nav/Footer here on
// purpose — the wordmark is the only way back home.
export function AuthShell({
  headline,
  sub,
  children,
}: {
  headline: string;
  sub: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-1 items-center justify-center px-4 py-10 sm:px-6">
      <div className="flex w-full max-w-4xl overflow-hidden rounded-2xl border border-line bg-card shadow-sm">
        <aside className="hidden w-1/2 flex-col justify-between bg-ink p-10 text-paper lg:flex">
          <Link href="/" className="font-display text-xl tracking-tight">
            Finhub<span className="italic">KH</span>
          </Link>
          <div>
            <div className="mb-10 rounded-xl border border-paper/15 p-4 text-paper/80">
              <div className="flex items-center justify-between text-xs">
                <span className="rounded bg-paper/10 px-2 py-0.5 font-medium tracking-wide">
                  LONG · BTCUSDT · 1h
                </span>
                <span>confidence 82%</span>
              </div>
              <p className="mt-3 font-mono text-xs">
                Entry 108,240&ensp;·&ensp;SL 106,900&ensp;·&ensp;TP 110,920
              </p>
              <p className="mt-2 text-xs italic text-paper/60">
                &ldquo;Momentum aligns with the news — the EMA cross held on
                the closed bar.&rdquo;
              </p>
            </div>
            <h2 className="mt-16 font-display text-3xl tracking-tight">
              {headline}
            </h2>
            <p className="mt-3 text-sm leading-relaxed text-paper/70">{sub}</p>
          </div>
        </aside>
        <main className="flex flex-1 items-center justify-center px-6 py-12 lg:px-12">
          <div className="w-full max-w-sm">
            <Link
              href="/"
              className="font-display text-xl tracking-tight lg:hidden"
            >
              Finhub<span className="italic">KH</span>
            </Link>
            <div className="mt-8 lg:mt-0">{children}</div>
          </div>
        </main>
      </div>
    </div>
  );
}
