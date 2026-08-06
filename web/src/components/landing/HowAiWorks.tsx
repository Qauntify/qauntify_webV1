"use client";

import { useEffect, useState } from "react";

const STEPS = [
  {
    id: "scan",
    label: "Rules scan",
    short: "Scan",
    detail: "Engine reads closed candles — EMA, RSI, MACD, structure.",
  },
  {
    id: "setup",
    label: "Setup found",
    short: "Setup",
    detail: "A candidate prints with entry, stop, and 2:1 targets.",
  },
  {
    id: "news",
    label: "News check",
    short: "News",
    detail: "Recent headlines are pulled in for context.",
  },
  {
    id: "ai",
    label: "AI confirm",
    short: "AI",
    detail: "SEA-LION reviews the chart + levels. Fail-closed.",
  },
  {
    id: "publish",
    label: "Published",
    short: "Live",
    detail: "Only confirms hit the feed — rejects are discarded.",
  },
] as const;

const HEADLINES = [
  "ETF inflows steady into BTC",
  "Dollar soft into London open",
  "No major FOMC risk this session",
];

const BARS = [42, 55, 48, 62, 58, 71, 66, 78, 74, 88, 82, 95];

const STEP_MS = 2200;

export function HowAiWorks({ compact = false }: { compact?: boolean }) {
  const [step, setStep] = useState(0);
  const [reduced, setReduced] = useState(false);

  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduced(mq.matches);
    const onChange = () => setReduced(mq.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  useEffect(() => {
    if (reduced) return;
    const id = window.setInterval(() => {
      setStep((s) => (s + 1) % STEPS.length);
    }, STEP_MS);
    return () => window.clearInterval(id);
  }, [reduced]);

  const active = STEPS[step];

  const panel = (
    <div
      className={`overflow-hidden border border-line bg-white ${
        compact ? "rounded-lg" : "rounded-lg"
      }`}
    >
      {/* Step pills */}
      <div className="flex border-b border-line bg-[#f8fafc]">
        {STEPS.map((s, i) => {
          const on = i === step;
          const done = i < step;
          return (
            <button
              key={s.id}
              type="button"
              onClick={() => setStep(i)}
              className={`flex flex-1 items-center justify-center gap-1 border-r border-line px-1 py-2 last:border-r-0 transition-colors ${
                on ? "bg-white" : "hover:bg-white/70"
              }`}
              title={s.label}
            >
              <span
                className={`flex h-4 w-4 items-center justify-center rounded font-mono text-[9px] font-bold ${
                  on
                    ? "bg-ink text-white"
                    : done
                      ? "bg-long text-white"
                      : "bg-line text-slate"
                }`}
              >
                {done && !on ? "✓" : i + 1}
              </span>
              <span
                className={`hidden text-[10px] font-semibold sm:inline ${
                  on ? "text-ink" : "text-slate"
                }`}
              >
                {s.short}
              </span>
            </button>
          );
        })}
      </div>

      {/* Stage */}
      <div
        className={`relative bg-[#0f172a] text-white ${
          compact ? "min-h-[260px] p-3 sm:p-3.5" : "min-h-[320px] p-4 sm:p-5"
        }`}
      >
        <div className="mb-2.5 flex items-center justify-between gap-2">
          <p className="font-mono text-[10px] font-semibold uppercase tracking-wider text-slate-400">
            {active.label}
          </p>
          <span className="inline-flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-wide text-emerald-400">
            <span
              className={`h-1.5 w-1.5 rounded-full bg-emerald-400 ${
                reduced ? "" : "hai-pulse"
              }`}
            />
            Running
          </span>
        </div>

        <div
          className={`rounded-md border border-white/10 bg-slate-900/80 p-2.5 transition-opacity ${
            step <= 1 ? "opacity-100" : "opacity-40"
          }`}
        >
          <div className="mb-1.5 flex items-center justify-between">
            <span className="font-mono text-[10px] text-slate-400">
              XAUUSD · 5m
            </span>
            {step >= 1 ? (
              <span className="rounded bg-emerald-500/20 px-1.5 py-0.5 font-mono text-[9px] font-semibold uppercase text-emerald-400">
                Long candidate
              </span>
            ) : (
              <span className="font-mono text-[10px] text-slate-500">
                scanning…
              </span>
            )}
          </div>
          <div
            className={`relative flex items-end gap-1 ${
              compact ? "h-16 sm:h-20" : "h-24 sm:h-28"
            }`}
          >
            {BARS.map((h, i) => (
              <div
                key={i}
                className={`flex-1 rounded-sm transition-colors duration-300 ${
                  step >= 1 && i >= BARS.length - 3
                    ? "bg-emerald-400"
                    : "bg-slate-600"
                }`}
                style={{ height: `${h}%` }}
              />
            ))}
            {step === 0 && !reduced ? (
              <div className="hai-scan-line pointer-events-none absolute inset-y-0 w-0.5 bg-white" />
            ) : null}
          </div>
          {step >= 1 ? (
            <div className="mt-2 grid grid-cols-3 gap-1.5 font-mono text-[9px] text-slate-300">
              <div>
                <span className="text-slate-500">Entry</span>
                <p className="font-semibold text-white">2,348.20</p>
              </div>
              <div>
                <span className="text-slate-500">SL</span>
                <p className="font-semibold text-rose-400">2,341.60</p>
              </div>
              <div>
                <span className="text-slate-500">TP</span>
                <p className="font-semibold text-emerald-400">2,361.40</p>
              </div>
            </div>
          ) : null}
        </div>

        <div
          className={`mt-2 overflow-hidden rounded-md border border-white/10 transition-all ${
            step === 2
              ? "bg-slate-900/80 opacity-100"
              : step > 2
                ? "bg-slate-900/40 opacity-50"
                : "max-h-0 border-0 opacity-0"
          }`}
        >
          {step >= 2 ? (
            <ul className="divide-y divide-white/5 px-2.5 py-0.5">
              {HEADLINES.map((h, i) => (
                <li
                  key={h}
                  className={`py-1.5 font-mono text-[10px] text-slate-300 ${
                    !reduced && step === 2 ? "hai-fade-in" : ""
                  }`}
                  style={
                    !reduced && step === 2
                      ? { animationDelay: `${i * 120}ms` }
                      : undefined
                  }
                >
                  <span className="mr-1.5 text-slate-500">▸</span>
                  {h}
                </li>
              ))}
            </ul>
          ) : null}
        </div>

        <div
          className={`mt-2 rounded-md border border-white/10 transition-all ${
            step >= 3
              ? "bg-slate-900/80 p-2.5 opacity-100"
              : "max-h-0 overflow-hidden border-0 p-0 opacity-0"
          }`}
        >
          {step >= 3 ? (
            <>
              <div className="flex items-center justify-between gap-2">
                <p className="font-mono text-[9px] font-semibold uppercase tracking-wider text-sky-300">
                  SEA-LION · reviewer
                </p>
                {step === 3 ? (
                  <span className="flex gap-1">
                    <span className="hai-dot h-1.5 w-1.5 rounded-full bg-sky-300" />
                    <span
                      className="hai-dot h-1.5 w-1.5 rounded-full bg-sky-300"
                      style={{ animationDelay: "0.15s" }}
                    />
                    <span
                      className="hai-dot h-1.5 w-1.5 rounded-full bg-sky-300"
                      style={{ animationDelay: "0.3s" }}
                    />
                  </span>
                ) : (
                  <span className="rounded bg-emerald-500/20 px-1.5 py-0.5 font-mono text-[9px] font-bold uppercase text-emerald-400">
                    Confirm
                  </span>
                )}
              </div>
              {step === 3 ? (
                <p className="mt-1.5 font-mono text-[10px] leading-relaxed text-slate-400">
                  Weighing structure · R:R · session fit…
                </p>
              ) : (
                <pre className="mt-1.5 overflow-x-auto font-mono text-[10px] leading-relaxed text-emerald-300/90">
{`{ "verdict": "confirm", "confidence": 74 }`}
                </pre>
              )}
            </>
          ) : null}
        </div>

        {step === 4 ? (
          <div
            className={`absolute right-3 top-3 rounded border-2 border-emerald-400 px-2 py-1 font-mono text-[10px] font-bold uppercase tracking-widest text-emerald-400 ${
              reduced ? "" : "hai-stamp"
            }`}
          >
            Live
          </div>
        ) : null}

        {step === 4 ? (
          <div
            className={`mt-2 rounded-md border border-emerald-500/30 bg-emerald-500/10 p-2.5 ${
              reduced ? "" : "hai-fade-in"
            }`}
          >
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="rounded bg-emerald-500/20 px-1.5 py-0.5 font-mono text-[9px] font-semibold uppercase text-emerald-400">
                Long
              </span>
              <span className="font-mono text-xs font-bold text-white">
                XAUUSD
              </span>
              <span className="rounded bg-white/10 px-1.5 py-0.5 font-mono text-[9px] uppercase text-slate-300">
                5m
              </span>
              <span className="ml-auto font-mono text-[10px] text-slate-400">
                74%
              </span>
            </div>
            <p className="mt-1.5 text-[10px] leading-relaxed text-slate-300">
              Published. Rejects never leave the engine.
            </p>
          </div>
        ) : null}
      </div>

      <div className="grid grid-cols-5 border-t border-line bg-[#f8fafc]">
        {STEPS.map((s, i) => (
          <div
            key={s.id}
            className={`h-1 transition-colors duration-300 ${
              i <= step ? "bg-ink" : "bg-transparent"
            }`}
          />
        ))}
      </div>
    </div>
  );

  if (compact) {
    return <div id="how-ai-works">{panel}</div>;
  }

  return (
    <section id="how-ai-works" className="border-b border-line bg-[#f1f5f9]">
      <div className="page-container py-5 md:py-6">
        <div className="mb-4 flex flex-wrap items-end justify-between gap-2">
          <div>
            <p className="font-mono text-[11px] font-semibold uppercase tracking-[0.14em] text-ink">
              Engine loop
            </p>
            <h2 className="mt-1 text-xl font-bold tracking-tight text-ink md:text-2xl">
              Watch how a signal gets made.
            </h2>
          </div>
          <p className="text-xs text-slate">Live demo · loops automatically</p>
        </div>
        {panel}
      </div>
    </section>
  );
}
