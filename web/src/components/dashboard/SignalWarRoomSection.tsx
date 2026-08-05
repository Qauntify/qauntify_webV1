"use client";

import { useEffect, useState } from "react";

import { getDebateForSignal, type Debate } from "@/lib/debates";

const VERDICT: Record<string, { label: string; cls: string }> = {
  agree: { label: "AGREE", cls: "bg-long-soft text-long" },
  reject: { label: "REJECT", cls: "bg-short-soft text-short" },
  caution: { label: "CAUTION", cls: "bg-accent-soft text-accent" },
};

function DebateBody({ debate }: { debate: Debate }) {
  const verdict = VERDICT[debate.managerVerdict] ?? VERDICT.caution;
  return (
    <div className="space-y-3">
      {debate.transcript.map((m, i) => (
        <div key={`${m.agent}-${i}`} className="flex gap-3">
          <span
            aria-hidden
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-line bg-card text-sm font-semibold text-slate"
          >
            {m.avatar || m.agent.slice(0, 1)}
          </span>
          <div className="min-w-0">
            <p className="text-xs font-semibold text-slate">{m.agent}</p>
            <p className="text-sm leading-relaxed text-ink">{m.message}</p>
          </div>
        </div>
      ))}
      <div className="flex items-center justify-between border-t border-line pt-3">
        <span className="text-xs text-slate">Manager verdict</span>
        <div className="flex items-center gap-2">
          <span className="font-mono text-xs text-slate">
            {debate.managerConfidence}%
          </span>
          <span
            className={`rounded-md px-2 py-0.5 font-mono text-[11px] font-semibold ${verdict.cls}`}
          >
            {verdict.label}
          </span>
        </div>
      </div>
    </div>
  );
}

/** War Room block shown on every signal detail — same layout with or without a debate. */
export function SignalWarRoomSection({ signalId }: { signalId: string }) {
  // The fetched debate is stored alongside the signalId it belongs to, so
  // switching signals falls back to the loading state by DERIVATION during
  // render. Resetting it with a setDebate(undefined) inside the effect body
  // does the same thing but costs an extra render pass, and trips
  // react-hooks/set-state-in-effect.
  const [loaded, setLoaded] = useState<{
    signalId: string;
    debate: Debate | null;
  } | null>(null);

  useEffect(() => {
    let cancelled = false;
    getDebateForSignal(signalId).then((row) => {
      if (!cancelled) setLoaded({ signalId, debate: row });
    });
    return () => {
      cancelled = true;
    };
  }, [signalId]);

  // undefined while this signal's debate is still in flight.
  const debate = loaded?.signalId === signalId ? loaded.debate : undefined;

  return (
    <div className="mt-5 rounded-lg border border-line bg-paper/40 p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <p className="text-xs font-medium uppercase tracking-wide text-slate">
          AI War Room
        </p>
        {debate ? (
          <span className="font-mono text-[10px] uppercase tracking-wide text-accent">
            Debate on file
          </span>
        ) : null}
      </div>
      {debate === undefined ? (
        <p className="text-sm text-slate">Loading debate…</p>
      ) : debate ? (
        <DebateBody debate={debate} />
      ) : (
        <p className="text-sm leading-relaxed text-slate">
          No war-room debate was recorded for this signal. Newer confirmed
          setups include the Structure, Momentum, and Manager exchange here.
        </p>
      )}
    </div>
  );
}
