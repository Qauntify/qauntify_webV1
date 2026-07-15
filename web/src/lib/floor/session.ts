const SESSION_WINDOWS = [
  ["Asia", 0, 9],
  ["London", 7, 16],
  ["New York", 12, 21],
] as const;

export function describeMarketSession(now = new Date()): string {
  const hour = now.getUTCHours() + now.getUTCMinutes() / 60;
  const active = SESSION_WINDOWS
    .filter(([, start, end]) => start <= hour && hour < end)
    .map(([name]) => name);
  const stamp = now.toISOString().slice(0, 16).replace("T", " UTC");

  if (!active.length) {
    return `Market session at ${stamp}: off-hours (no major FX session)`;
  }
  if (active.length === 1) {
    return `Market session at ${stamp}: ${active[0]}`;
  }
  return `Market session at ${stamp}: ${active.join(" / ")} overlap (active: ${active.join(", ")})`;
}
