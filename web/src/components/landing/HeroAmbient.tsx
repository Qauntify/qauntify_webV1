const CANDLES = [
  "up",
  "up",
  "down",
  "up",
  "down",
  "up",
  "down",
  "up",
  "up",
  "down",
  "up",
  "up",
] as const;

const TICKS = [
  { sym: "XAUUSD", chg: "+0.42%", up: true },
  { sym: "BTCUSD", chg: "+1.18%", up: true },
  { sym: "EURUSD", chg: "-0.21%", up: false },
  { sym: "ETHUSD", chg: "+0.87%", up: true },
  { sym: "GBPUSD", chg: "-0.09%", up: false },
  { sym: "NAS100", chg: "+0.55%", up: true },
];

export function HeroAmbient() {
  const ticker = [...TICKS, ...TICKS];

  return (
    <div className="hero-ambient-bg" aria-hidden>
      <div className="hero-ambient-ticker">
        <div className="hero-ambient-ticker-track">
          {ticker.map((t, i) => (
            <span key={`${t.sym}-${i}`} className="hero-tick">
              <span className="sym">{t.sym}</span>
              <span className={t.up ? "up" : "dn"}>{t.chg}</span>
            </span>
          ))}
        </div>
      </div>

      <div className="hero-ambient-chart">
        {CANDLES.map((dir, i) => (
          <div key={i} className={`hero-candle is-${dir}`}>
            <span className="hero-candle-wick" />
            <span className="hero-candle-body" />
          </div>
        ))}
      </div>

      <svg
        className="hero-ambient-line"
        viewBox="0 0 600 180"
        preserveAspectRatio="none"
      >
        <path d="M0 140 C 40 138, 70 120, 100 110 S 160 95, 190 100 S 250 130, 290 90 S 350 40, 390 55 S 450 95, 490 70 S 550 35, 600 28" />
      </svg>
    </div>
  );
}
