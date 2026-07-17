"use client";

import { FLOOR_DESKS, type FloorDesk, type FloorRunPhase, type FloorRunStatus } from "@/lib/floor/types";

export type DeskHuntState = "active" | "done" | "waiting" | "sleeping";

const DESK_ORDER: FloorDesk[] = ["macro", "technical", "news", "pm"];

const PARTY: Record<
  FloorDesk,
  { codename: string; role: string; mark: string; charge: number }
> = {
  macro: { codename: "ORBIT", role: "Strategist", mark: "OR", charge: 72 },
  technical: { codename: "VECTOR", role: "Scout", mark: "VT", charge: 88 },
  news: { codename: "PULSE", role: "Intel", mark: "PL", charge: 64 },
  pm: { codename: "APEX", role: "Commander", mark: "AX", charge: 96 },
};

export function deskHuntState(desk: FloorDesk, phase: FloorRunPhase): DeskHuntState {
  if (phase === "sleeping" || phase === "idle") return "sleeping";
  if (phase === desk) return "active";
  const current = DESK_ORDER.indexOf(phase as FloorDesk);
  const mine = DESK_ORDER.indexOf(desk);
  if (current === -1) return "waiting";
  return mine < current ? "done" : "waiting";
}

function stateLabel(state: DeskHuntState): string {
  if (state === "active") return "IN COMBAT";
  if (state === "done") return "CLEARED";
  if (state === "sleeping") return "COOLDOWN";
  return "QUEUED";
}

function chargeWidth(state: DeskHuntState, base: number): string {
  if (state === "done") return "100%";
  if (state === "active") return `${Math.min(100, base)}%`;
  if (state === "sleeping") return "35%";
  return "12%";
}

function AvatarMark({ desk, state }: { desk: FloorDesk; state: DeskHuntState }) {
  const { mark } = PARTY[desk];
  return (
    <div className={`floor-avatar floor-avatar--${desk} floor-avatar--${state}`} aria-hidden="true">
      <span className="floor-avatar-ring" />
      <span className="floor-avatar-core">{mark}</span>
      {state === "active" ? <span className="floor-avatar-scan" /> : null}
    </div>
  );
}

function PartyAgent({
  desk,
  state,
}: {
  desk: FloorDesk;
  state: DeskHuntState;
}) {
  const agent = PARTY[desk];

  return (
    <article
      className={`floor-party-card floor-party-card--${state}`}
      data-desk={desk}
      aria-label={`${agent.codename} ${stateLabel(state)}`}
    >
      <div className="floor-party-card-top">
        <AvatarMark desk={desk} state={state} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-2">
            <p className="floor-party-code">{agent.codename}</p>
            <span className="floor-party-badge">{agent.role}</span>
          </div>
          <p className={`floor-party-state floor-party-state--${state}`}>
            {stateLabel(state)}
          </p>
        </div>
      </div>

      <div className="floor-party-meter" aria-hidden="true">
        <div className="floor-party-meter-label">
          <span>CHARGE</span>
          <span>{state === "active" ? "SCANNING" : state === "done" ? "MAX" : "IDLE"}</span>
        </div>
        <div className="floor-party-meter-track">
          <div
            className="floor-party-meter-fill"
            style={{ width: chargeWidth(state, agent.charge) }}
          />
        </div>
      </div>
    </article>
  );
}

function HuntPipeline({ phase }: { phase: FloorRunPhase }) {
  return (
    <ol className="floor-pipeline" aria-label="Hunt pipeline">
      {DESK_ORDER.map((desk, index) => {
        const state = deskHuntState(desk, phase);
        return (
          <li key={desk} className={`floor-pipeline-step floor-pipeline-step--${state}`}>
            {index > 0 ? <span className="floor-pipeline-link" aria-hidden="true" /> : null}
            <span className="floor-pipeline-node">{PARTY[desk].mark}</span>
            <span className="floor-pipeline-name">{PARTY[desk].codename}</span>
          </li>
        );
      })}
    </ol>
  );
}

export function FloorRobot({ status }: { status: FloorRunStatus }) {
  if (!status.running) return null;

  const xp = Math.max(1, status.cycle) * 120;
  const stage =
    status.phase === "sleeping"
      ? "Cooldown between raids"
      : status.phase === "pm"
        ? "Boss turn — Commander decides signal or pass"
        : "Party clearing the desk queue";

  return (
    <section
      className="floor-raid-panel rounded-2xl border border-line bg-card p-5"
      aria-label="Gold hunt party"
      aria-live="polite"
    >
      <div className="floor-raid-header">
        <div>
          <p className="floor-raid-eyebrow">RAID ACTIVE · GOLD HUNT</p>
          <h3 className="floor-raid-title">Party online — cycle {status.cycle || 1}</h3>
          <p className="mt-1 text-sm text-slate">{stage}</p>
        </div>
        <div className="floor-raid-stats" aria-label="Raid stats">
          <div>
            <span className="floor-raid-stat-label">XP</span>
            <span className="floor-raid-stat-value">{xp}</span>
          </div>
          <div>
            <span className="floor-raid-stat-label">TARGET</span>
            <span className="floor-raid-stat-value">PAXG</span>
          </div>
        </div>
      </div>

      <HuntPipeline phase={status.phase} />

      {status.lastMessage ? (
        <p className="floor-raid-log font-mono text-xs text-ink">{status.lastMessage}</p>
      ) : null}

      <div className="floor-party-grid">
        {FLOOR_DESKS.map((desk) => (
          <PartyAgent
            key={desk}
            desk={desk}
            state={deskHuntState(desk, status.phase)}
          />
        ))}
      </div>
    </section>
  );
}
