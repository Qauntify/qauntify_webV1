import { SectionHeader } from "@/components/shared/SectionHeader";

const MARKETS = [
  { name: "Bitcoin", symbol: "BTCUSD", live: true },
  { name: "Ethereum", symbol: "ETHUSD", live: true },
  { name: "Gold", symbol: "XAUUSD", live: true },
  { name: "GBP", symbol: "GBPUSD", live: true },
  { name: "Stocks", symbol: "AAPL +", live: false },
  { name: "Indices", symbol: "NAS100 +", live: false },
];

export function Markets() {
  return (
    <section id="markets" className="section-block">
      <div className="page-container py-16 md:py-20">
        <SectionHeader
          eyebrow="Markets"
          title="Four markets live. More when they earn it."
          subtitle="We only list a market once the engine actually trades it well."
        />
        <div className="mt-10 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          {MARKETS.map((m) => (
            <div
              key={m.name}
              className={`stat-tile ${m.live ? "" : "opacity-50"}`}
            >
              <p className="font-semibold">{m.name}</p>
              <p className="mt-1 font-mono text-xs text-slate">{m.symbol}</p>
              <p
                className={`mt-3 inline-block rounded px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${
                  m.live
                    ? "bg-long-soft text-long"
                    : "bg-line text-slate"
                }`}
              >
                {m.live ? "Live" : "Soon"}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
