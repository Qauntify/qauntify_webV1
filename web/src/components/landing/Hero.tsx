import Link from "next/link";

import { HeroAmbient } from "@/components/landing/HeroAmbient";
import { HowAiWorks } from "@/components/landing/HowAiWorks";
import type { Stats } from "@/lib/signals";

export function Hero({ stats }: { stats: Stats }) {
  const statItems = [
    { value: String(stats.total), label: "Signals logged" },
    {
      value: stats.total > 0 ? `${stats.avgConfidence}%` : "—",
      label: "Avg confidence",
    },
    {
      value: stats.winRate !== null ? `${stats.winRate}%` : "—",
      label: "Win rate",
      good: stats.winRate !== null && stats.winRate >= 50,
    },
  ];

  return (
    <section className="hero-ambient flex min-h-[calc(100dvh-4rem)] flex-col border-b border-line">
      <HeroAmbient />

      <div className="page-container relative z-10 grid flex-1 items-center gap-6 py-6 md:grid-cols-[1fr_1.05fr] md:gap-8 md:py-8 lg:grid-cols-[1fr_0.95fr]">
        <div className="flex flex-col">
          <p className="font-mono text-[11px] font-semibold uppercase tracking-[0.18em] text-ink">
            Qauntify
          </p>
          <h1 className="mt-2 text-[1.85rem] font-extrabold leading-[1.08] tracking-tight text-ink sm:text-4xl lg:text-[2.5rem]">
            Trade with clarity.
            <span className="block text-slate">Not guesswork.</span>
          </h1>
          <p className="mt-3 max-w-md text-sm leading-relaxed text-slate">
            Rules scan the chart. AI confirms the setup. You get entry, stop,
            targets, and a plain-language rationale — logged live.
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

        <HowAiWorks compact />
      </div>

      <div className="relative z-10 shrink-0 border-t border-line bg-[#f1f5f9]">
        <div className="page-container grid grid-cols-3 divide-x divide-line">
          {statItems.map((item) => (
            <div
              key={item.label}
              className="px-3 py-3.5 text-center sm:px-6 sm:py-4 sm:text-left"
            >
              <p
                className={`font-mono text-lg font-bold tracking-tight sm:text-xl ${
                  item.good ? "text-long" : "text-ink"
                }`}
              >
                {item.value}
              </p>
              <p className="mt-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate">
                {item.label}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
