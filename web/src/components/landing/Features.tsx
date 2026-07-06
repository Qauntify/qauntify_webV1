const FEATURES = [
  {
    title: "Technical scanning",
    body: "EMA 9/21 crossovers filtered by RSI and MACD momentum on 1-hour candles — setups are found by rules, not vibes.",
  },
  {
    title: "AI confirmation",
    body: "Every candidate setup is reviewed by SEA-LION before it becomes a signal. No confirmation, no signal.",
  },
  {
    title: "News context",
    body: "Recent headlines are read alongside the chart, so a technically clean setup gets rejected when the news says otherwise.",
  },
  {
    title: "Risk defined up front",
    body: "Stops sit beyond the recent swing with an ATR buffer; targets are set at 2:1 reward-to-risk. Always.",
  },
  {
    title: "Plain-language rationale",
    body: "Each signal explains itself in a short paragraph — what lined up, and why the AI confirmed it.",
  },
  {
    title: "Fail-closed discipline",
    body: "If the AI errors, times out, or answers unclearly, the setup is discarded. An unconfirmed signal is never published.",
  },
];

export function Features() {
  return (
    <section id="features" className="border-b border-line">
      <div className="mx-auto max-w-6xl px-6 py-20">
        <p className="text-xs font-medium uppercase tracking-[0.2em] text-slate">
          Features
        </p>
        <h2 className="mt-3 max-w-lg font-display text-4xl tracking-tight">
          A signal is a checklist, not a hunch.
        </h2>
        <div className="mt-12 grid gap-px overflow-hidden rounded-xl border border-line bg-line sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((f) => (
            <div key={f.title} className="bg-white p-6">
              <h3 className="font-medium">{f.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-slate">{f.body}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
