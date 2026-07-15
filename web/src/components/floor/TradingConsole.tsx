import type { FloorDesk } from "@/lib/floor/types";

/** Multi-monitor trading console silhouette (institutional desk, not a character). */
export function TradingConsole({
  desk,
  active,
}: {
  desk: FloorDesk;
  active: boolean;
}) {
  return (
    <svg
      viewBox="0 0 200 110"
      className={`trading-console ${active ? "trading-console--live" : "trading-console--standby"}`}
      role="img"
      aria-label={`${desk} multi-monitor console`}
    >
      <defs>
        <linearGradient id={`glow-${desk}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#67e8f9" stopOpacity="0.35" />
          <stop offset="100%" stopColor="#0ea5e9" stopOpacity="0.05" />
        </linearGradient>
      </defs>

      {/* Desk surface */}
      <path
        d="M10 88 H190 L175 102 H25 Z"
        className="trading-console__desk"
      />
      <rect x="20" y="84" width="160" height="6" rx="1" className="trading-console__rail" />

      {/* Monitor arm post */}
      <rect x="96" y="52" width="8" height="32" className="trading-console__arm" />

      {/* Top row monitors */}
      <g className="trading-console__screens">
        <rect x="28" y="18" width="42" height="30" rx="2" className="trading-console__bezel" />
        <rect x="31" y="21" width="36" height="24" className="trading-console__panel" fill={`url(#glow-${desk})`} />
        <rect x="79" y="12" width="42" height="36" rx="2" className="trading-console__bezel" />
        <rect x="82" y="15" width="36" height="30" className="trading-console__panel trading-console__panel--main" fill={`url(#glow-${desk})`} />
        <rect x="130" y="18" width="42" height="30" rx="2" className="trading-console__bezel" />
        <rect x="133" y="21" width="36" height="24" className="trading-console__panel" fill={`url(#glow-${desk})`} />
      </g>

      {/* Lower / ultrawide row */}
      <rect x="48" y="50" width="104" height="22" rx="2" className="trading-console__bezel" />
      <rect x="51" y="53" width="98" height="16" className="trading-console__panel trading-console__panel--wide" fill={`url(#glow-${desk})`} />

      {/* Chart ticks on main panel */}
      <polyline
        points="86,40 92,34 98,36 104,28 110,32"
        className="trading-console__chart"
        fill="none"
      />
      <polyline
        points="55,65 70,62 85,66 100,58 115,60 130,56"
        className="trading-console__chart trading-console__chart--wide"
        fill="none"
      />

      {/* Keyboard + mouse pad */}
      <rect x="70" y="90" width="48" height="6" rx="1" className="trading-console__kb" />
      <rect x="124" y="91" width="10" height="5" rx="1" className="trading-console__kb" />
    </svg>
  );
}
