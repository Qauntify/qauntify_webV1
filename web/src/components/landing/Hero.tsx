import Link from "next/link";

import { HeroAmbient } from "@/components/landing/HeroAmbient";
import { HowAiWorks } from "@/components/landing/HowAiWorks";
import type { Stats } from "@/lib/signals";

export function Hero({ stats }: { stats: Stats }) {
  return (
    <section className="hero-ambient flex min-h-[calc(100dvh-4rem)] flex-col border-b border-line">
      <HeroAmbient />

      <div className="page-container relative z-10 grid flex-1 items-center gap-6 py-6 md:grid-cols-[1fr_1.05fr] md:gap-8 md:py-8 lg:grid-cols-[1fr_0.95fr]">
        <div className="flex flex-col">
          <div className="flex flex-wrap items-center gap-2">
            <p className="font-mono text-[11px] font-semibold uppercase tracking-[0.18em] text-ink">
              Qauntify
            </p>
            <span className="rounded-full bg-long-soft px-2 py-0.5 font-mono text-[10px] font-bold uppercase tracking-wide text-long">
              Free · no account needed
            </span>
          </div>
          <h1 className="mt-2 text-[1.85rem] font-extrabold leading-[1.08] tracking-tight text-ink sm:text-4xl lg:text-[2.5rem]">
            Built in the open.
            <span className="block text-slate">Traded together.</span>
          </h1>
          <p className="mt-3 max-w-md text-sm leading-relaxed text-slate">
            Rules scan the chart. AI confirms the setup. Every entry, stop,
            target, and rationale is logged live for the whole community to
            see — free for every trader, no black box, no gatekeeping.
          </p>
          <div className="mt-5 flex flex-wrap items-center gap-2.5">
            <Link href="/signals" className="btn-primary">
              View signals
            </Link>
            <Link href="/track-record" className="btn-secondary">
              Track record
            </Link>
            <Link
              href="/war-room"
              className="px-2 text-sm font-semibold text-slate hover:text-ink"
            >
              War Room →
            </Link>
          </div>
        </div>

        <HowAiWorks stats={stats} />
      </div>
    </section>
  );
}
