import Link from "next/link";

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
    <div className="flex min-h-full flex-1 items-center justify-center bg-paper px-4 py-10">
      <div className="flex w-full max-w-4xl overflow-hidden rounded-xl border border-line bg-card shadow-lg">
        <aside className="hidden w-5/12 flex-col justify-between bg-accent p-10 text-white lg:flex">
          <Link href="/" className="text-lg font-bold">
            Finhub<span className="opacity-80">KH</span>
          </Link>
          <div>
            <div className="rounded-lg border border-white/20 bg-white/10 p-4 backdrop-blur-sm">
              <div className="flex items-center justify-between text-xs font-medium">
                <span className="rounded bg-long/20 px-2 py-0.5 text-long-soft">
                  LONG · BTCUSDT
                </span>
                <span>82%</span>
              </div>
              <p className="mt-3 font-mono text-xs">
                Entry 108,240 · SL 106,900 · TP 110,920
              </p>
              <p className="mt-2 text-xs text-white/70">
                Momentum aligns with the news — EMA cross held on the closed bar.
              </p>
            </div>
            <h2 className="mt-10 text-2xl font-bold">{headline}</h2>
            <p className="mt-3 text-sm leading-relaxed text-white/80">{sub}</p>
          </div>
        </aside>
        <main className="flex flex-1 items-center justify-center px-6 py-12 lg:px-12">
          <div className="w-full max-w-sm">
            <Link href="/" className="text-lg font-bold lg:hidden">
              Finhub<span className="text-accent">KH</span>
            </Link>
            <div className="mt-8 lg:mt-0">{children}</div>
          </div>
        </main>
      </div>
    </div>
  );
}
