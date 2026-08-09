// Prices: thousands separators; fewer decimals for large numbers.
export function formatPrice(value: number): string {
  const decimals = Math.abs(value) >= 1000 ? 0 : 2;
  return value.toLocaleString("km-KH", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

/** Display label for stored timeframe / lane ids. */
export function formatTimeframe(timeframe: string): string {
  if (timeframe === "bbma") return "BBMA";
  if (timeframe === "floor") return "ជាន់";
  return timeframe;
}

// Absolute timestamp; "never" for null.
export function formatDateTime(iso: string | null): string {
  if (!iso) return "មិនដែល";
  return new Date(iso).toLocaleString("km-KH", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

// Relative time from an ISO timestamp.
export function formatRelativeTime(iso: string, now: Date = new Date()): string {
  const then = new Date(iso);
  const seconds = Math.floor((now.getTime() - then.getTime()) / 1000);
  if (Number.isNaN(seconds) || seconds < 0) return "ឥឡូវនេះ";
  if (seconds < 60) return "ឥឡូវនេះ";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} នាទីមុន`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} ម៉ោងមុន`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days} ថ្ងៃមុន`;
  return then.toLocaleDateString("km-KH", { month: "short", day: "numeric", year: "numeric" });
}
