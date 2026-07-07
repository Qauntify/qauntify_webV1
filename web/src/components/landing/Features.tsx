import { SectionHeader } from "@/components/shared/SectionHeader";

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

export function Features() {
  return (
    <section id="features" className="section-block">
      <div className="page-container py-16 md:py-20">
        <SectionHeader
          eyebrow="Features"
          title="A signal is a checklist, not a hunch."
        />
        <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((f) => (
            <div key={f.title} className="stat-tile">
              <h3 className="font-semibold text-ink">{f.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-slate">{f.body}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
