import type { FloorDesk, FloorTone } from "@/lib/floor/types";

const SHELL: Record<FloorDesk, string> = {
  macro: "#1a6b7a",
  technical: "#2f5d4a",
  news: "#7a5a1a",
  pm: "#3d4a7a",
};

type RobotMode = "idle" | "working" | "warming";

export function FloorRobot({
  desk,
  tone,
  mode,
}: {
  desk: FloorDesk;
  tone?: FloorTone;
  mode: RobotMode;
}) {
  const shell = SHELL[desk];
  const lamp =
    tone === "bullish" ? "#3dd68c" : tone === "cautious" ? "#f0b429" : "#8b9bb4";

  return (
    <svg
      viewBox="0 0 120 140"
      className={`floor-robot floor-robot--${mode}`}
      role="img"
      aria-label={`${desk} desk robot ${mode}`}
    >
      <ellipse cx="60" cy="128" rx="28" ry="6" className="floor-robot__shadow" />
      <rect x="34" y="78" width="52" height="36" rx="8" fill={shell} className="floor-robot__torso" />
      <rect x="42" y="86" width="36" height="18" rx="3" className="floor-robot__chest-panel" />
      <circle cx="50" cy="95" r="2.5" fill={lamp} className="floor-robot__led" />
      <circle cx="60" cy="95" r="2.5" fill={lamp} className="floor-robot__led floor-robot__led--delay" />
      <circle cx="70" cy="95" r="2.5" fill={lamp} className="floor-robot__led floor-robot__led--delay-2" />

      <g className="floor-robot__arm floor-robot__arm--left">
        <rect x="18" y="84" width="16" height="8" rx="4" fill={shell} />
        <rect x="12" y="98" width="10" height="14" rx="3" className="floor-robot__hand" />
      </g>
      <g className="floor-robot__arm floor-robot__arm--right">
        <rect x="86" y="84" width="16" height="8" rx="4" fill={shell} />
        <rect x="98" y="98" width="10" height="14" rx="3" className="floor-robot__hand" />
      </g>

      <g className="floor-robot__head">
        <rect x="40" y="36" width="40" height="36" rx="10" fill={shell} />
        <rect x="46" y="46" width="28" height="16" rx="4" className="floor-robot__visor" />
        <rect x="50" y="50" width="8" height="8" rx="1" className="floor-robot__eye" />
        <rect x="62" y="50" width="8" height="8" rx="1" className="floor-robot__eye floor-robot__eye--right" />
        <line x1="60" y1="28" x2="60" y2="36" className="floor-robot__antenna-stem" />
        <circle cx="60" cy="24" r="4" fill={lamp} className="floor-robot__antenna" />
      </g>

      <g className="floor-robot__screen">
        <rect x="22" y="112" width="76" height="10" rx="2" className="floor-robot__desk" />
        <rect x="30" y="104" width="26" height="10" rx="1" className="floor-robot__monitor" />
        <rect x="64" y="106" width="20" height="6" rx="1" className="floor-robot__keyboard" />
      </g>
    </svg>
  );
}
