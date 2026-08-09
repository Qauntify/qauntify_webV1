import type { EquityPoint } from "@/lib/track-record";

export function EquityCurve({ points }: { points: EquityPoint[] }) {
  if (points.length < 2) {
    return <div className="text-sm text-slate/60">មិនទាន់មានការជួញដូរបិទគ្រប់គ្រាន់ដើម្បីគូសខ្សែស្មើភាព។</div>;
  }
  const W = 720;
  const H = 160;
  const pad = 6;
  const rs = points.map((p) => p.r);
  const max = Math.max(...rs, 0);
  const min = Math.min(...rs, 0);
  const span = max - min || 1;
  const x = (i: number) => pad + (i / (points.length - 1)) * (W - 2 * pad);
  const y = (r: number) => H - pad - ((r - min) / span) * (H - 2 * pad);
  const line = points.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p.r).toFixed(1)}`).join(" ");
  const area = `${line} L${x(points.length - 1).toFixed(1)},${(H - pad).toFixed(1)} L${x(0).toFixed(1)},${(H - pad).toFixed(1)} Z`;
  const stroke = points[points.length - 1].r >= 0 ? "#34d399" : "#fb7185";
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="ខ្សែស្មើភាព R សរុប">
      <defs>
        <linearGradient id="eq-grad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor={stroke} stopOpacity="0.25" />
          <stop offset="1" stopColor={stroke} stopOpacity="0" />
        </linearGradient>
      </defs>
      <line x1={pad} y1={y(0)} x2={W - pad} y2={y(0)} stroke="rgba(148,163,184,.3)" strokeDasharray="3 3" />
      <path d={area} fill="url(#eq-grad)" />
      <path d={line} fill="none" stroke={stroke} strokeWidth="2" />
    </svg>
  );
}
