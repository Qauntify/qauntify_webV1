import Link from "next/link";

import { SectionHeader } from "@/components/shared/SectionHeader";

const FAQS = [
  {
    q: "What exactly is a signal?",
    a: "A trade setup the engine found and the AI confirmed: symbol, direction, entry, stop loss, take profit, confidence score, and rationale.",
  },
  {
    q: "How does the AI confirmation work?",
    a: "Technical rules propose a setup first. SEA-LION reviews the candidate with indicator readings and news headlines, then confirms or rejects.",
  },
  {
    q: "Does it track TP and SL hits?",
    a: "Yes. Open signals are checked every engine run. When price hits take profit or stop loss, the status updates and you get a Telegram alert.",
  },
  {
    q: "Why are there sometimes no new signals?",
    a: "Crossovers with aligned momentum are infrequent by design. A quiet dashboard means nothing worth your attention was found.",
  },
  {
    q: "Is this financial advice?",
    a: "No. Signals are for education and analysis only. Trading involves risk and you can lose money.",
  },
];

export function Faq() {
  return (
    <>
      <section id="faq" className="section-block">
        <div className="page-container py-16 md:py-20">
          <SectionHeader eyebrow="FAQ" title="Fair questions." />
          <div className="mt-10 max-w-2xl divide-y divide-line">
            {FAQS.map((item) => (
              <details key={item.q} className="group py-4">
                <summary className="flex cursor-pointer list-none items-center justify-between font-semibold">
                  {item.q}
                  <span className="ml-4 text-accent transition-transform group-open:rotate-45">
                    +
                  </span>
                </summary>
                <p className="mt-3 text-sm leading-relaxed text-slate">{item.a}</p>
              </details>
            ))}
          </div>
        </div>
      </section>
      <section className="section-block bg-accent">
        <div className="page-container py-14 text-center">
          <h2 className="text-3xl font-bold text-white">
            See what the engine sees.
          </h2>
          <p className="mx-auto mt-3 max-w-md text-sm text-white/80">
            Free account. Full signal history. Outcome tracking included.
          </p>
          <Link
            href="/signup"
            className="mt-6 inline-block rounded-lg bg-white px-6 py-3 text-sm font-semibold text-accent hover:bg-white/90"
          >
            Create free account
          </Link>
        </div>
      </section>
    </>
  );
}
