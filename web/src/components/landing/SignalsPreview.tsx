import Link from "next/link";

import { TradeTicket } from "@/components/shared/TradeTicket";
import type { Signal } from "@/lib/signals";

export function SignalsPreview({ signals }: { signals: Signal[] }) {
  return (
    <section id="signals" className="border-b border-line bg-paper">
      <div className="page-container py-5 md:py-6">
        <div className="flex flex-wrap items-end justify-between gap-2">
          <div>
            <p className="font-mono text-[11px] font-semibold uppercase tracking-[0.14em] text-ink">
              Live signals
            </p>
            <h2 className="mt-1 text-xl font-bold tracking-tight text-ink md:text-2xl">
              Straight from the engine
            </h2>
          </div>
          <Link href="/signals" className="text-sm font-semibold text-ink hover:text-slate">
            View all →
          </Link>
        </div>

        {signals.length > 0 ? (
          <div className="mt-4 grid gap-2.5 md:grid-cols-3">
            {signals.slice(0, 3).map((s) => (
              <TradeTicket key={s.id} signal={s} showRationale={false} />
            ))}
          </div>
        ) : (
          <div className="mt-4 rounded-lg border border-dashed border-line bg-card p-6 text-center text-sm text-slate">
            No signals yet — the engine publishes here the moment a setup is
            confirmed.
          </div>
        )}
      </div>
    </section>
  );
}
