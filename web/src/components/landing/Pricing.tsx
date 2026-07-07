import Link from "next/link";

import { SectionHeader } from "@/components/shared/SectionHeader";

const TIERS = [
  {
    name: "Free",
    price: "$0",
    tagline: "Everything you need to evaluate us.",
    features: [
      "Full dashboard access",
      "Signal history with rationale",
      "Win rate and outcome tracking",
    ],
    cta: "Create free account",
    href: "/signup",
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
    <section id="pricing" className="section-block bg-card">
      <div className="page-container py-16 md:py-20">
        <SectionHeader eyebrow="Pricing" title="Free while we prove it." />
        <div className="mt-10 grid gap-5 md:max-w-3xl md:grid-cols-2">
          {TIERS.map((tier) => (
            <div
              key={tier.name}
              className={`stat-tile flex flex-col ${!tier.disabled ? "ring-1 ring-accent/30" : ""}`}
            >
              <div className="flex items-baseline justify-between">
                <h3 className="text-lg font-bold">{tier.name}</h3>
                <p className="font-mono text-2xl font-bold">{tier.price}</p>
              </div>
              <p className="mt-1 text-sm text-slate">{tier.tagline}</p>
              <ul className="mt-5 flex flex-1 flex-col gap-2.5 text-sm">
                {tier.features.map((f) => (
                  <li key={f} className="flex gap-2">
                    <span className="font-bold text-long">✓</span>
                    <span>{f}</span>
                  </li>
                ))}
              </ul>
              {tier.href ? (
                <Link href={tier.href} className="btn-primary mt-6 text-center">
                  {tier.cta}
                </Link>
              ) : (
                <span className="btn-secondary mt-6 cursor-not-allowed text-center opacity-60">
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
