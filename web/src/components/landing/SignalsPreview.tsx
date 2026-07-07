import Link from "next/link";

import { SectionHeader } from "@/components/shared/SectionHeader";
import { TradeTicket } from "@/components/shared/TradeTicket";
import type { Signal } from "@/lib/signals";

export function SignalsPreview({ signals }: { signals: Signal[] }) {
  return (
    <section id="signals" className="section-block bg-card">
      <div className="page-container py-16 md:py-20">
        <SectionHeader eyebrow="Live signals" title="Straight from the engine.">
          <Link href="/dashboard" className="link-arrow">
            View all →
          </Link>
        </SectionHeader>
        {signals.length > 0 ? (
          <div className="mt-10 grid gap-5 md:grid-cols-3">
            {signals.slice(0, 3).map((s) => (
              <TradeTicket key={s.id} signal={s} showRationale={false} />
            ))}
          </div>
        ) : (
          <div className="mt-10 rounded-lg border border-dashed border-line p-10 text-center text-sm text-slate">
            No signals yet — the engine publishes here the moment a setup is
            confirmed.
          </div>
        )}
      </div>
    </section>
  );
}
