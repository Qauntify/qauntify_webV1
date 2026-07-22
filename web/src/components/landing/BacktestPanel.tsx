import { SectionHeader } from "@/components/shared/SectionHeader";

// Backtested snapshot of the three live session strategies. Numbers come from
// `python -m signals.backtest` (scale-out fills, HTF confluence as live) — a
// dated snapshot, not a live feed. Re-run and update AS_OF + ROWS to refresh.
const AS_OF = "22 Jul 2026";

type Row = {
  name: string;
  timeframe: string;
  session: string;
  hitRate: number; // % of backtested signals that reached their first target
  expR: number; // average return per signal, in R (multiple of risk)
  trades: number;
  windowDays: number;
};

const ROWS: Row[] = [
  { name: "Support / Resistance", timeframe: "15m", session: "Scalp", hitRate: 58, expR: 0.33, trades: 62, windowDays: 12 },
  { name: "ICT / SMC structure", timeframe: "1h", session: "Swing", hitRate: 67, expR: 0.44, trades: 6, windowDays: 47 },
  { name: "ICT Fair Value Gap", timeframe: "5m", session: "Super-scalp", hitRate: 56, expR: -0.02, trades: 23, windowDays: 5 },
];

function expTone(r: number): string {
  if (r > 0.05) return "text-long";
  if (r < -0.05) return "text-short";
  return "text-slate";
}

function fmtR(r: number): string {
  return `${r >= 0 ? "+" : "−"}${Math.abs(r).toFixed(2)}R`;
}

export function BacktestPanel() {
  return (
    <section id="performance" className="section-block">
      <div className="page-container py-16 md:py-20">
        <SectionHeader
          eyebrow="Backtested"
          title="How the strategies scored in testing."
          subtitle={`Each strategy replayed over recent market data — the share of signals that reached their first target, and the average return per signal in R (a multiple of the risk taken). Snapshot as of ${AS_OF}.`}
        />

        <div className="mt-10 grid gap-6 lg:grid-cols-3">
          {ROWS.map((row, i) => (
            <div
              key={row.name}
              className="stat-tile animate-fade-up"
              style={{ animationDelay: `${i * 100}ms` }}
            >
              <div className="flex items-center justify-between gap-2">
                <h3 className="font-semibold text-ink">{row.name}</h3>
                <span className="rounded-md bg-accent-soft px-2 py-0.5 font-mono text-xs font-medium text-accent">
                  {row.timeframe}
                </span>
              </div>
              <p className="mt-0.5 text-xs text-slate">{row.session} session</p>

              <div className="mt-5 flex items-baseline justify-between">
                <span className="text-xs text-slate">Reached first target</span>
                <span className="font-mono text-2xl font-bold text-ink">{row.hitRate}%</span>
              </div>
              <div
                className="mt-2 h-2 w-full overflow-hidden rounded-full bg-line"
                role="img"
                aria-label={`${row.hitRate}% of backtested signals reached their first target`}
              >
                <div className="h-full rounded-full bg-accent" style={{ width: `${row.hitRate}%` }} />
              </div>

              <div className="mt-5 flex items-center justify-between border-t border-line pt-4">
                <div>
                  <p className="text-xs text-slate">Avg / signal</p>
                  <p className={`font-mono font-semibold ${expTone(row.expR)}`}>{fmtR(row.expR)}</p>
                </div>
                <div className="text-right">
                  <p className="text-xs text-slate">Sample</p>
                  <p className="font-mono font-semibold text-ink">
                    {row.trades} · {row.windowDays}d
                  </p>
                </div>
              </div>
            </div>
          ))}
        </div>

        <p className="mt-8 max-w-3xl text-xs leading-relaxed text-slate">
          Backtested, hypothetical results from a rules-only replay over recent
          Kraken / COMEX candles (test window shown per strategy). They exclude
          the live AI confirmation step, slippage, and fees, and rest on small
          samples. Backtested performance is not indicative of future results and
          is not financial advice.
        </p>
      </div>
    </section>
  );
}
