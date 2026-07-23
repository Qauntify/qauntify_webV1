"use client";

import { useEffect, useRef, useState } from "react";

import type { Debate } from "@/lib/debates";

// Signature colour per robot: Technical = brand indigo, Fundamental = gold
// (we trade gold), Manager = violet authority.
const BOT_COLORS = ["var(--accent)", "#eab308", "#8b5cf6"];

const VERDICT: Record<string, { label: string; color: string }> = {
  agree: { label: "AGREE", color: "var(--long)" },
  reject: { label: "REJECT", color: "var(--short)" },
  caution: { label: "CAUTION", color: "#eab308" },
};

function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReduced(mq.matches);
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, []);
  return reduced;
}

function Robot({
  color,
  active,
  delay,
}: {
  color: string;
  active: boolean;
  delay: number;
}) {
  return (
    <div
      className={`wr-robot ${active ? "wr-active" : ""}`}
      style={{ ["--bot" as string]: color, animationDelay: `${delay}ms` }}
    >
      <svg viewBox="0 0 80 100" className="h-20 w-16 md:h-24 md:w-20" aria-hidden>
        {/* antenna */}
        <line x1="40" y1="6" x2="40" y2="18" stroke="var(--slate)" strokeWidth="2" />
        <circle className="wr-antenna" cx="40" cy="6" r="4" fill={color} />
        {/* head */}
        <rect x="12" y="18" width="56" height="42" rx="14" fill="var(--card)" stroke="var(--line)" strokeWidth="2" />
        {/* visor */}
        <rect x="18" y="26" width="44" height="20" rx="10" fill="var(--ink)" opacity="0.9" />
        {/* eyes */}
        <circle className="wr-eye" cx="32" cy="36" r="4" fill={color} />
        <circle className="wr-eye" cx="48" cy="36" r="4" fill={color} />
        {/* mouth */}
        <rect className="wr-mouth" x="33" y="50" width="14" height="5" rx="2.5" fill={color} opacity="0.85" />
        {/* body */}
        <rect x="18" y="62" width="44" height="32" rx="12" fill="var(--card)" stroke="var(--line)" strokeWidth="2" />
        {/* chest core */}
        <circle className="wr-core" cx="40" cy="78" r="6" fill={color} />
      </svg>
    </div>
  );
}

export function WarRoomStage({ debate }: { debate: Debate }) {
  const msgs = debate.transcript.slice(0, 3);
  const reduced = usePrefersReducedMotion();
  const [step, setStep] = useState(0); // active speaker index; == msgs.length when done
  const [typed, setTyped] = useState("");
  const [runId, setRunId] = useState(0);
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);

  useEffect(() => {
    const pending = timers.current;
    pending.forEach(clearTimeout);
    pending.length = 0;
    // Reduced motion / no data: don't animate and don't setState here — the
    // render derives "done" from `reduced` below.
    if (reduced || msgs.length === 0) return;
    let cancelled = false;
    const play = (idx: number) => {
      if (cancelled) return;
      if (idx >= msgs.length) {
        setStep(msgs.length);
        return;
      }
      setStep(idx);
      setTyped("");
      const full = msgs[idx].message;
      let c = 0;
      const tick = () => {
        if (cancelled) return;
        c += 1;
        setTyped(full.slice(0, c));
        pending.push(
          setTimeout(c < full.length ? tick : () => play(idx + 1), c < full.length ? 16 : 950),
        );
      };
      pending.push(setTimeout(tick, 400));
    };
    // Defer the first step so no setState runs synchronously in the effect body.
    pending.push(setTimeout(() => play(0), 0));
    return () => {
      cancelled = true;
      pending.forEach(clearTimeout);
    };
  }, [runId, reduced, msgs]);

  const done = reduced || msgs.length === 0 || step >= msgs.length;
  const activeIndex = done ? msgs.length - 1 : step;
  const verdict = VERDICT[debate.managerVerdict] ?? VERDICT.caution;
  const isLong = debate.direction === "long";

  return (
    <div className="overflow-hidden rounded-2xl border border-line bg-card">
      {/* console header */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="wr-live-dot" />
          <span className="font-mono text-xs font-semibold uppercase tracking-widest text-slate">
            AI War Room
          </span>
        </div>
        <div className="flex items-center gap-2 font-mono text-xs">
          <span className="font-semibold text-ink">{debate.symbol}</span>
          <span className="rounded bg-accent-soft px-1.5 py-0.5 text-accent">{debate.timeframe}</span>
          <span className={`rounded px-1.5 py-0.5 font-semibold ${isLong ? "bg-long-soft text-long" : "bg-short-soft text-short"}`}>
            {isLong ? "LONG" : "SHORT"}
          </span>
        </div>
      </div>

      {/* stage */}
      <div className="wr-stage relative px-4 py-6">
        <div className="grid grid-cols-3 gap-2">
          {msgs.map((m, i) => (
            <div key={i} className="flex flex-col items-center gap-1">
              <Robot color={BOT_COLORS[i] ?? "var(--accent)"} active={i === activeIndex} delay={i * 400} />
              <p className="text-center text-[11px] font-semibold leading-tight text-slate">
                {m.agent}
              </p>
              {i === activeIndex && !done ? (
                <span className="wr-speaking font-mono text-[10px] text-accent">● speaking</span>
              ) : (
                <span className="text-[10px] text-transparent">·</span>
              )}
            </div>
          ))}
        </div>

        {/* dialogue box */}
        <div className="mt-5 min-h-23 rounded-xl border border-line bg-paper/60 p-4">
          {!done ? (
            <>
              <p className="mb-1 font-mono text-[11px] font-semibold uppercase tracking-wide" style={{ color: BOT_COLORS[activeIndex] }}>
                {msgs[activeIndex]?.avatar} {msgs[activeIndex]?.agent}
              </p>
              <p className="text-sm leading-relaxed text-ink">
                {typed}
                <span className="wr-caret">▌</span>
              </p>
            </>
          ) : (
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="min-w-0">
                <p className="mb-1 font-mono text-[11px] font-semibold uppercase tracking-wide text-slate">
                  🧑‍💼 Manager&apos;s call
                </p>
                <p className="text-sm leading-relaxed text-ink">{msgs[msgs.length - 1]?.message}</p>
              </div>
              <div className="wr-stamp shrink-0 text-center" style={{ ["--stamp" as string]: verdict.color }}>
                <span className="wr-stamp-label font-mono text-lg font-black tracking-wider">
                  {verdict.label}
                </span>
                <span className="mt-1 block font-mono text-xs text-slate">
                  {debate.managerConfidence}% confident
                </span>
              </div>
            </div>
          )}
        </div>

        {/* confidence meter + replay */}
        <div className="mt-4 flex items-center gap-3">
          <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-line">
            <div
              className="h-full rounded-full transition-[width] duration-700 ease-out"
              style={{ width: done ? `${debate.managerConfidence}%` : "0%", background: verdict.color }}
            />
          </div>
          <button
            type="button"
            onClick={() => setRunId((r) => r + 1)}
            className="shrink-0 rounded-full border border-line px-3 py-1 font-mono text-xs text-slate transition-colors hover:border-accent hover:text-accent"
          >
            ↻ Replay
          </button>
        </div>
      </div>
    </div>
  );
}
