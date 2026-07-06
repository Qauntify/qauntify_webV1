const MARKETS = [
  { name: "Bitcoin", symbol: "BTCUSDT", live: true },
  { name: "Ethereum", symbol: "ETHUSDT", live: true },
  { name: "Gold", symbol: "XAUUSD", live: false },
  { name: "Forex", symbol: "EURUSD +", live: false },
  { name: "Stocks", symbol: "AAPL +", live: false },
  { name: "Indices", symbol: "NAS100 +", live: false },
];

export function Markets() {
  return (
    <section id="markets" className="border-b border-line">
      <div className="mx-auto max-w-6xl px-6 py-20">
        <p className="text-xs font-medium uppercase tracking-[0.2em] text-slate">
          Markets
        </p>
        <h2 className="mt-3 font-display text-4xl tracking-tight">
          Two markets live. More when they earn it.
        </h2>
        <p className="mt-4 max-w-lg text-sm leading-relaxed text-slate">
          We only list a market once the engine actually trades it well. BTC
          and ETH are live today; the rest are on the bench.
        </p>
        <div className="mt-10 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
          {MARKETS.map((m) => (
            <div
              key={m.name}
              className={`rounded-xl border p-4 ${
                m.live
                  ? "border-line bg-card"
                  : "border-dashed border-line bg-transparent opacity-60"
              }`}
            >
              <p className="font-medium">{m.name}</p>
              <p className="mt-1 font-mono text-xs text-slate">{m.symbol}</p>
              <p
                className={`mt-3 inline-block rounded px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wide ${
                  m.live ? "bg-long-soft text-long" : "bg-line text-slate"
                }`}
              >
                {m.live ? "live" : "coming soon"}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
