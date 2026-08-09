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
      <div className="flex w-full max-w-4xl overflow-hidden rounded-xl border border-line bg-card">
        <aside className="hidden w-5/12 flex-col justify-between bg-ink p-10 text-white lg:flex">
          <Link href="/" className="text-lg font-bold">
            Qaunt<span className="text-white/70">ify</span>
          </Link>
          <div>
            <div className="rounded-lg border border-white/15 bg-white/5 p-4">
              <div className="flex items-center justify-between text-xs font-medium">
                <span className="rounded border border-long/40 bg-long/15 px-2 py-0.5 text-long">
                  ទិញ · BTCUSD
                </span>
                <span className="font-mono">82%</span>
              </div>
              <p className="mt-3 font-mono text-xs text-white/90">
                ចូល 108,240 · SL 106,900 · TP 110,920
              </p>
              <p className="mt-2 text-xs text-white/60">
                សន្ទុះស្របនឹងព័ត៌មាន — EMA cross នៅតែរក្សានៅរបារបិទ។
              </p>
            </div>
            <h2 className="mt-10 text-2xl font-bold">{headline}</h2>
            <p className="mt-3 text-sm leading-relaxed text-white/70">{sub}</p>
          </div>
        </aside>
        <main className="flex flex-1 items-center justify-center px-6 py-12 lg:px-12">
          <div className="w-full max-w-sm">
            <Link href="/" className="text-lg font-bold lg:hidden">
              Qaunt<span className="text-slate">ify</span>
            </Link>
            <div className="mt-8 lg:mt-0">{children}</div>
          </div>
        </main>
      </div>
    </div>
  );
}
