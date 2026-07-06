const TIERS = [
  {
    name: "Free",
    price: "$0",
    tagline: "Everything you need to evaluate us.",
    features: [
      "Full dashboard access",
      "Signal history with rationale",
      "Engine stats, updated live",
    ],
    cta: "Open the dashboard",
    href: "/dashboard",
    disabled: false,
  },
  {
    name: "Pro",
    price: "TBA",
    tagline: "For traders who want signals pushed to them.",
    features: [
      "Real-time Telegram alerts",
      "Early access to new markets",
      "Priority support",
    ],
    cta: "Coming soon",
    href: null,
    disabled: true,
  },
];

export function Pricing() {
  return (
    <section id="pricing" className="border-b border-line bg-card">
      <div className="mx-auto max-w-6xl px-6 py-20">
        <p className="text-xs font-medium uppercase tracking-[0.2em] text-slate">
          Pricing
        </p>
        <h2 className="mt-3 font-display text-4xl tracking-tight">
          Free while we prove it.
        </h2>
        <div className="mt-10 grid gap-6 md:max-w-3xl md:grid-cols-2">
          {TIERS.map((tier) => (
            <div key={tier.name} className="flex flex-col rounded-xl border border-line bg-paper p-7">
              <div className="flex items-baseline justify-between">
                <h3 className="font-medium">{tier.name}</h3>
                <p className="font-mono text-2xl font-semibold">{tier.price}</p>
              </div>
              <p className="mt-1 text-sm text-slate">{tier.tagline}</p>
              <ul className="mt-5 flex flex-col gap-2 text-sm">
                {tier.features.map((f) => (
                  <li key={f} className="flex gap-2">
                    <span className="text-long">✓</span>
                    <span>{f}</span>
                  </li>
                ))}
              </ul>
              {tier.href ? (
                <a
                  href={tier.href}
                  className="mt-7 rounded-lg bg-ink px-4 py-2.5 text-center text-sm font-medium text-paper hover:bg-ink/85"
                >
                  {tier.cta}
                </a>
              ) : (
                <span className="mt-7 cursor-not-allowed rounded-lg border border-line px-4 py-2.5 text-center text-sm font-medium text-slate">
                  {tier.cta}
                </span>
              )}
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
