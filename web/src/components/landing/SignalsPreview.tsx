import Link from "next/link";

import { TradeTicket } from "@/components/shared/TradeTicket";
import type { Signal } from "@/lib/signals";

export function SignalsPreview({ signals }: { signals: Signal[] }) {
  return (
    <section id="signals" className="border-b border-line bg-card">
      <div className="mx-auto max-w-6xl px-6 py-20">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="text-xs font-medium uppercase tracking-[0.2em] text-slate">
              Live signals
            </p>
            <h2 className="mt-3 font-display text-4xl tracking-tight">
              Straight from the engine.
            </h2>
          </div>
          <Link
            href="/dashboard"
            className="text-sm font-medium underline-offset-4 hover:underline"
          >
            View all →
          </Link>
        </div>
        {signals.length > 0 ? (
          <div className="mt-10 grid gap-6 md:grid-cols-3">
            {signals.slice(0, 3).map((s) => (
              <TradeTicket key={s.id} signal={s} showRationale={false} />
            ))}
          </div>
        ) : (
          <div className="mt-10 rounded-xl border border-dashed border-line p-10 text-center text-sm text-slate">
            No signals yet — the engine publishes here the moment a setup is
            confirmed. Crossovers are infrequent by design.
          </div>
        )}
      </div>
    </section>
  );
}
