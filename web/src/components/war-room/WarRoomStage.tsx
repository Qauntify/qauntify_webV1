"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import type { Debate } from "@/lib/debates";

/** Trading-floor party kit — teal / gold / navy, no neon purple. */
const AGENTS = [
  {
    id: "structure",
    title: "Structure",
    className: "Level Runner",
    color: "#0d9488",
    seat: "wr-seat-0",
  },
  {
    id: "momentum",
    title: "Momentum",
    className: "Momentum Scout",
    color: "#ca8a04",
    seat: "wr-seat-1",
  },
  {
    id: "mgr",
    title: "Manager",
    className: "Floor Chief",
    color: "#1e3a5f",
    seat: "wr-seat-2",
  },
] as const;

const VERDICT: Record<string, { label: string; color: string }> = {
  agree: { label: "AGREE", color: "var(--long)" },
  reject: { label: "REJECT", color: "var(--short)" },
  caution: { label: "CAUTION", color: "#ca8a04" },
};

const WALK_MS = 900;

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

function GameAvatar({
  role,
  speaking,
  dimmed,
}: {
  role: 0 | 1 | 2;
  speaking?: boolean;
  dimmed?: boolean;
}) {
  const accent = AGENTS[role].color;
  return (
    <div
      className={`wr-avatar ${speaking ? "wr-avatar-speak" : ""} ${dimmed ? "wr-avatar-dim" : ""}`}
      style={{ ["--bot" as string]: accent }}
      aria-hidden
    >
      <svg viewBox="0 0 96 128" className="h-full w-full drop-shadow-md">
        {/* shadow */}
        <ellipse cx="48" cy="120" rx="22" ry="5" fill="currentColor" opacity="0.12" />
        {/* boots */}
        <rect x="28" y="104" width="16" height="10" rx="3" fill="#1a1a1a" />
        <rect x="52" y="104" width="16" height="10" rx="3" fill="#1a1a1a" />
        {/* legs */}
        <rect x="32" y="86" width="12" height="22" rx="4" fill={role === 1 ? "#1e293b" : "#0f172a"} />
        <rect x="52" y="86" width="12" height="22" rx="4" fill={role === 1 ? "#1e293b" : "#0f172a"} />
        {/* coat / torso */}
        <path
          d="M24 50 L48 44 L72 50 L68 88 L28 88 Z"
          fill={role === 0 ? "#134e4a" : role === 1 ? "#292524" : "#172554"}
          stroke={accent}
          strokeWidth="1.5"
        />
        {/* chest plate / badge */}
        <rect x="40" y="58" width="16" height="18" rx="3" fill={accent} opacity="0.9" />
        {role === 0 ? (
          <path d="M43 72 L48 62 L53 72" fill="none" stroke="#ecfdf5" strokeWidth="1.5" />
        ) : role === 1 ? (
          <circle cx="48" cy="67" r="4" fill="#fef9c3" />
        ) : (
          <path d="M44 64h8v8h-8z" fill="#e2e8f0" opacity="0.9" />
        )}
        {/* arms */}
        <rect x="14" y="52" width="12" height="28" rx="5" fill={role === 0 ? "#115e59" : role === 1 ? "#44403c" : "#1e3a8a"} />
        <rect x="70" y="52" width="12" height="28" rx="5" fill={role === 0 ? "#115e59" : role === 1 ? "#44403c" : "#1e3a8a"} />
        {/* tool in hand */}
        {role === 0 ? (
          <rect x="8" y="74" width="14" height="10" rx="2" fill="#042f2e" stroke={accent} strokeWidth="1" />
        ) : role === 1 ? (
          <rect x="74" y="70" width="12" height="16" rx="1" fill="#fef3c7" stroke={accent} strokeWidth="1" />
        ) : (
          <rect x="74" y="68" width="10" height="14" rx="1" fill="#cbd5e1" stroke={accent} strokeWidth="1" />
        )}
        {/* head */}
        <circle cx="48" cy="30" r="16" fill="#f5d0b0" stroke="#c4a484" strokeWidth="1" />
        {/* hair / helm */}
        {role === 0 ? (
          <path d="M32 28 Q48 8 64 28 L60 22 Q48 12 36 22 Z" fill="#0f766e" />
        ) : role === 1 ? (
          <path d="M30 26 Q48 10 66 26 L64 20 Q48 6 32 20 Z" fill="#44403c" />
        ) : (
          <>
            <rect x="30" y="14" width="36" height="12" rx="3" fill="#0f172a" stroke={accent} strokeWidth="1" />
            <rect x="38" y="10" width="20" height="6" rx="2" fill="#334155" />
          </>
        )}
        {/* visor / eyes */}
        <rect x="36" y="28" width="24" height="10" rx="4" fill="#0f172a" opacity="0.92" />
        <circle className="wr-eye" cx="42" cy="33" r="2.2" fill={accent} />
        <circle className="wr-eye" cx="54" cy="33" r="2.2" fill={accent} />
        {/* mouth */}
        <rect className="wr-mouth" x="44" y="42" width="8" height="2.5" rx="1" fill="#9a6b4f" />
      </svg>
    </div>
  );
}

function Desk({
  role,
  label,
  classLabel,
  occupied,
  activeSeat,
}: {
  role: 0 | 1 | 2;
  label: string;
  classLabel: string;
  occupied: boolean;
  activeSeat: boolean;
}) {
  const color = AGENTS[role].color;
  return (
    <div className={`wr-desk ${activeSeat ? "wr-desk-hot" : ""}`} style={{ ["--bot" as string]: color }}>
      <div className="wr-desk-nameplate">
        <span className="wr-desk-class">{classLabel}</span>
        <span className="wr-desk-title">{label}</span>
      </div>
      <div className="wr-desk-slot">
        {occupied ? (
          <GameAvatar role={role} dimmed={!activeSeat} />
        ) : (
          <div className="wr-empty-chair" aria-hidden>
            <span>away</span>
          </div>
        )}
      </div>
      <div className="wr-tabletop">
        <div className="wr-table-screen" />
        <div className="wr-table-leg" />
      </div>
    </div>
  );
}

export function WarRoomStage({
  debate,
  fullScreen = false,
}: {
  debate: Debate;
  fullScreen?: boolean;
}) {
  const msgs = useMemo(() => debate.transcript.slice(0, 3), [debate]);
  const reduced = usePrefersReducedMotion();
  const [step, setStep] = useState(0);
  const [phase, setPhase] = useState<"walk" | "speak" | "done">("walk");
  const [typed, setTyped] = useState("");
  const [thinking, setThinking] = useState(true);
  const [runId, setRunId] = useState(0);
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);

  useEffect(() => {
    const pending = timers.current;
    pending.forEach(clearTimeout);
    pending.length = 0;
    if (reduced || msgs.length === 0) {
      return;
    }
    let cancelled = false;

    const play = (idx: number) => {
      if (cancelled) return;
      if (idx >= msgs.length) {
        setStep(msgs.length);
        setPhase("done");
        return;
      }
      setStep(idx);
      setPhase("walk");
      setTyped("");
      setThinking(true);

      const afterWalk = () => {
        if (cancelled) return;
        setPhase("speak");
        const full = msgs[idx].message;
        let c = 0;
        const tick = () => {
          if (cancelled) return;
          c += 1;
          setTyped(full.slice(0, c));
          pending.push(
            setTimeout(
              c < full.length ? tick : () => play(idx + 1),
              c < full.length ? 14 : 700,
            ),
          );
        };
        pending.push(
          setTimeout(() => {
            if (cancelled) return;
            setThinking(false);
            tick();
          }, 700),
        );
      };

      pending.push(setTimeout(afterWalk, WALK_MS));
    };

    pending.push(setTimeout(() => play(0), 0));
    return () => {
      cancelled = true;
      pending.forEach(clearTimeout);
    };
  }, [runId, reduced, msgs]);

  const done = reduced || msgs.length === 0 || phase === "done" || step >= msgs.length;
  const activeIndex = done
    ? Math.max(0, msgs.length - 1)
    : Math.min(step, Math.max(0, msgs.length - 1));
  const atPodium = !reduced && !done;
  const walking = atPodium && phase === "walk";
  const verdict = VERDICT[debate.managerVerdict] ?? VERDICT.caution;
  const isLong = debate.direction === "long";

  return (
    <div
      className={
        fullScreen
          ? "flex h-full min-h-0 flex-col overflow-hidden border-0 bg-[#0b1220]"
          : "overflow-hidden rounded-2xl border border-line bg-[#0b1220]"
      }
    >
      <div className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-b border-white/10 px-4 py-3 lg:px-8">
        <div className="flex items-center gap-2">
          <span className="wr-live-dot" />
          <span className="font-mono text-xs font-semibold uppercase tracking-widest text-teal-200/80">
            Live Stage
          </span>
        </div>
        <div className="flex items-center gap-2 font-mono text-xs">
          <span className="font-semibold text-white">{debate.symbol}</span>
          <span className="rounded bg-teal-500/20 px-1.5 py-0.5 text-teal-300">
            {debate.timeframe}
          </span>
          <span
            className={`rounded px-1.5 py-0.5 font-semibold ${
              isLong ? "bg-emerald-500/20 text-emerald-300" : "bg-rose-500/20 text-rose-300"
            }`}
          >
            {isLong ? "LONG" : "SHORT"}
          </span>
        </div>
      </div>

      <div
        className={
          fullScreen
            ? "relative flex min-h-0 flex-1 flex-col overflow-hidden"
            : "relative flex flex-col"
        }
      >
        <div className="wr-arena relative min-h-[280px] flex-1 md:min-h-[340px]">
          <div className="wr-arena-haze" aria-hidden />
          <div className="wr-floor-grid" aria-hidden />

          {/* three desks */}
          <div className="wr-desk-row">
            {AGENTS.map((agent, i) => {
              const role = i as 0 | 1 | 2;
              const seatEmpty = atPodium && activeIndex === i;
              return (
                <Desk
                  key={agent.id}
                  role={role}
                  label={msgs[i]?.agent ?? agent.title}
                  classLabel={agent.className}
                  occupied={!seatEmpty}
                  activeSeat={!done && activeIndex === i && !seatEmpty}
                />
              );
            })}
          </div>

          {/* walk path + podium */}
          <div className="wr-podium-zone">
            <div className="wr-walk-path" aria-hidden />
            <div className="wr-podium">
              <span className="wr-podium-label">PODIUM</span>
              {atPodium ? (
                <div
                  key={`${runId}-${activeIndex}-${phase}`}
                  className={`wr-walker ${walking ? "wr-walker-in" : "wr-walker-speak"} wr-from-${activeIndex}`}
                >
                  <GameAvatar role={activeIndex as 0 | 1 | 2} speaking={!walking && phase === "speak"} />
                </div>
              ) : done ? (
                <div className="wr-walker wr-walker-speak wr-from-2">
                  <GameAvatar role={2} speaking />
                </div>
              ) : null}
            </div>
          </div>
        </div>

        {/* dialogue HUD */}
        <div
          className={
            fullScreen
              ? "relative z-10 mx-4 mb-4 mt-auto flex min-h-0 max-h-[38%] flex-col overflow-hidden rounded-xl border border-teal-500/25 bg-[#0a1628]/95 p-4 backdrop-blur md:mx-8 md:mb-6 md:p-6"
              : "relative z-10 m-4 flex flex-col rounded-xl border border-teal-500/25 bg-[#0a1628]/95 p-4"
          }
        >
          {!done ? (
            <>
              <div className="mb-2 flex items-center justify-between gap-2">
                <p
                  className="font-mono text-[11px] font-semibold uppercase tracking-wide"
                  style={{ color: AGENTS[activeIndex as 0 | 1 | 2].color }}
                >
                  {walking
                    ? `${msgs[activeIndex]?.agent ?? AGENTS[activeIndex as 0 | 1 | 2].title} walking to podium…`
                    : msgs[activeIndex]?.agent ?? AGENTS[activeIndex as 0 | 1 | 2].title}
                </p>
                <span className="font-mono text-[10px] uppercase tracking-widest text-slate-400">
                  Turn {Math.min(activeIndex + 1, msgs.length)} / {msgs.length}
                </span>
              </div>
              {walking || thinking ? (
                <p
                  className="flex items-center gap-1.5"
                  style={{ color: AGENTS[activeIndex as 0 | 1 | 2].color }}
                >
                  <span className="wr-dot" />
                  <span className="wr-dot" />
                  <span className="wr-dot" />
                  <span className="ml-1 font-mono text-xs text-slate-400">
                    {walking ? "crossing the floor…" : "preparing call…"}
                  </span>
                </p>
              ) : (
                <p
                  className={`overflow-y-auto leading-relaxed text-slate-100 ${
                    fullScreen ? "text-base md:text-lg" : "text-sm"
                  }`}
                >
                  {typed}
                  <span className="wr-caret">▌</span>
                </p>
              )}
            </>
          ) : (
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="min-w-0">
                <p className="mb-1 font-mono text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                  Floor Chief — final call
                </p>
                <p
                  className={`leading-relaxed text-slate-100 ${
                    fullScreen ? "text-base md:text-lg" : "text-sm"
                  }`}
                >
                  {msgs[msgs.length - 1]?.message}
                </p>
              </div>
              <div
                className="wr-stamp shrink-0 text-center"
                style={{ ["--stamp" as string]: verdict.color }}
              >
                <span className="wr-stamp-label font-mono text-lg font-black tracking-wider">
                  {verdict.label}
                </span>
                <span className="mt-1 block font-mono text-xs text-slate-400">
                  {debate.managerConfidence}% confident
                </span>
              </div>
            </div>
          )}

          <div className="mt-4 flex shrink-0 items-center gap-3">
            <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-white/10">
              <div
                className="h-full rounded-full transition-[width] duration-700 ease-out"
                style={{
                  width: done ? `${debate.managerConfidence}%` : `${((activeIndex + (done ? 1 : phase === "speak" ? 0.55 : 0.2)) / Math.max(msgs.length, 1)) * 100}%`,
                  background: done ? verdict.color : AGENTS[activeIndex as 0 | 1 | 2].color,
                }}
              />
            </div>
            <button
              type="button"
              onClick={() => setRunId((r) => r + 1)}
              className="shrink-0 rounded-full border border-white/15 px-3 py-1 font-mono text-xs text-slate-300 transition-colors hover:border-teal-400 hover:text-teal-300"
            >
              Replay
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
