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
    <section id="features" className="border-b border-line bg-card">
      <div className="page-container py-6 md:py-7">
        <div className="mb-4">
          <p className="font-mono text-[11px] font-semibold uppercase tracking-[0.14em] text-ink">
            How it works
          </p>
          <h2 className="mt-1 text-xl font-bold tracking-tight text-ink md:text-2xl">
            A signal is a checklist, not a hunch.
          </h2>
        </div>

        <div className="grid gap-px overflow-hidden rounded-lg border border-line bg-line sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((f) => (
            <div key={f.title} className="bg-paper p-4">
              <h3 className="text-sm font-semibold text-ink">{f.title}</h3>
              <p className="mt-1.5 text-xs leading-relaxed text-slate sm:text-[13px]">
                {f.body}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
