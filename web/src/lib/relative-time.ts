export function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const h = Math.floor(diff / 3.6e6);
  if (h < 1) return "ឥឡូវនេះ";
  if (h < 24) return `${h} ម៉ោងមុន`;
  const d = Math.floor(h / 24);
  return d === 1 ? "ម្សិលមិញ" : `${d} ថ្ងៃមុន`;
}
