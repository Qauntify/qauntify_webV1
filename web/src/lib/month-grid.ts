export type MonthCell = { dateStr: string; dayNum: number; inMonth: boolean };

function iso(year: number, month0: number, day: number): string {
  const mm = String(month0 + 1).padStart(2, "0");
  const dd = String(day).padStart(2, "0");
  return `${year}-${mm}-${dd}`;
}

// Monday-start calendar grid for `month` (0-11), padded with the tail of the
// previous month and the head of the next month so it fills whole weeks.
// dateStr is formatted from the integer date parts (no Date timezone
// conversion) so it compares directly against dailyNet's date keys.
export function buildMonthGrid(year: number, month: number): MonthCell[] {
  const firstDow = new Date(year, month, 1).getDay(); // 0=Sun..6=Sat
  const lead = (firstDow + 6) % 7; // days shown before the 1st (Monday start)
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const daysInPrev = new Date(year, month, 0).getDate();
  const prevMonth = month === 0 ? 11 : month - 1;
  const prevYear = month === 0 ? year - 1 : year;
  const nextMonth = month === 11 ? 0 : month + 1;
  const nextYear = month === 11 ? year + 1 : year;

  const cells: MonthCell[] = [];
  for (let i = lead - 1; i >= 0; i--) {
    const day = daysInPrev - i;
    cells.push({ dateStr: iso(prevYear, prevMonth, day), dayNum: day, inMonth: false });
  }
  for (let day = 1; day <= daysInMonth; day++) {
    cells.push({ dateStr: iso(year, month, day), dayNum: day, inMonth: true });
  }
  const trail = (7 - (cells.length % 7)) % 7;
  for (let day = 1; day <= trail; day++) {
    cells.push({ dateStr: iso(nextYear, nextMonth, day), dayNum: day, inMonth: false });
  }
  return cells;
}
