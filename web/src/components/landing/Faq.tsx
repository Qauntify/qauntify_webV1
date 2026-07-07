import Link from "next/link";

const FAQS = [
  {
    q: "What exactly is a signal?",
    a: "A trade setup the engine found and the AI confirmed: symbol, direction, entry price, stop loss, take profit, a 0–100 confidence score, and a short written rationale.",
  },
  {
    q: "How does the AI confirmation work?",
    a: "Technical rules propose a setup first. The candidate — with its indicator readings and recent news headlines — is then reviewed by the SEA-LION model, which confirms or rejects it. Rejected setups are never published.",
  },
  {
    q: "Which markets are covered?",
    a: "Bitcoin (BTCUSDT) and Ethereum (ETHUSDT) on 1-hour candles today. More markets are added only after the engine handles them well.",
  },
  {
    q: "Why are there sometimes no new signals?",
    a: "Crossovers with aligned momentum are infrequent by design. A quiet dashboard means the rules found nothing worth your attention — not that the engine is down.",
  },
  {
    q: "Is this financial advice?",
    a: "No. Signals are for education and analysis only. Trading involves risk and you can lose money. Always do your own research.",
  },
];

export function Faq() {
  return (
    <>
      <section id="faq" className="border-b border-line">
        <div className="mx-auto max-w-6xl px-6 py-20">
          <p className="text-xs font-medium uppercase tracking-[0.2em] text-slate">
            FAQ
          </p>
          <h2 className="mt-3 font-display text-4xl tracking-tight">
            Fair questions.
          </h2>
          <div className="mt-10 max-w-2xl divide-y divide-line">
            {FAQS.map((item) => (
              <details key={item.q} className="group py-4">
                <summary className="flex cursor-pointer list-none items-center justify-between font-medium">
                  {item.q}
                  <span className="text-slate transition-transform group-open:rotate-45">
                    +
                  </span>
                </summary>
                <p className="mt-3 text-sm leading-relaxed text-slate">{item.a}</p>
              </details>
            ))}
          </div>
        </div>
      </section>
      <section className="border-b border-line bg-card">
        <div className="mx-auto max-w-6xl px-6 py-16 text-center">
          <h2 className="font-display text-4xl tracking-tight">
            See what the engine sees.
          </h2>
          <Link
            href="/signup"
            className="mt-6 inline-block rounded-lg bg-ink px-5 py-3 text-sm font-medium text-paper hover:bg-ink/85"
          >
            Create free account
          </Link>
        </div>
      </section>
    </>
  );
}
