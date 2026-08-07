import { DailyPnLCalendar } from "@/components/shared/DailyPnLCalendar";
import type { DailyPnL } from "@/lib/signals";

const FEATURES = [
  {
    title: "Technical scanning",
    body: "EMA 9/21 crossovers filtered by RSI and MACD on 1-hour candles — setups are found by rules, not vibes.",
  },
  {
    title: "AI confirmation",
    body: "Every candidate is reviewed by SEA-LION before it becomes a signal. No confirmation, no signal.",
  },
  {
    title: "News context",
    body: "Recent headlines are read alongside the chart so a clean setup gets rejected when news says otherwise.",
  },
  {
    title: "Risk defined up front",
    body: "Stops beyond the recent swing with an ATR buffer; targets at 2:1 reward-to-risk. Always.",
  },
  {
    title: "Outcome tracking",
    body: "Open signals are monitored every run. When price hits TP or SL, status updates automatically.",
  },
  {
    title: "Fail-closed discipline",
    body: "If the AI errors or answers unclearly, the setup is discarded. Unconfirmed signals are never published.",
  },
];

export function Features({ dailyPnL }: { dailyPnL: DailyPnL[] }) {
  return (
    <section
      id="features"
      className="flex min-h-[calc(100dvh-4rem)] items-center border-b border-line bg-card"
    >
      <div className="mx-auto grid w-full max-w-[100rem] gap-10 px-6 py-10 md:py-14 lg:grid-cols-[0.6fr_1.4fr] lg:items-center lg:gap-16 xl:px-10">
        <div>
          <p className="font-mono text-[11px] font-semibold uppercase tracking-[0.14em] text-ink">
            How it works
          </p>
          <h2 className="mt-1 text-xl font-bold tracking-tight text-ink md:text-2xl">
            A signal is a checklist, not a hunch.
          </h2>

          <ul className="mt-6 flex flex-col gap-4">
            {FEATURES.map((f) => (
              <li key={f.title} className="flex gap-3">
                <span
                  className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-long-soft text-[11px] font-bold text-long"
                  aria-hidden
                >
                  ✓
                </span>
                <div>
                  <h3 className="text-sm font-semibold text-ink">{f.title}</h3>
                  <p className="mt-0.5 text-[13px] leading-relaxed text-slate">
                    {f.body}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        </div>

        <div>
          <DailyPnLCalendar
            data={dailyPnL}
            description={null}
            interactive={false}
            compact
          />
        </div>
      </div>
    </section>
  );
}
