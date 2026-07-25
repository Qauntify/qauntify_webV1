import { describe, it, expect } from "vitest";
import { buildMonthGrid } from "@/lib/month-grid";

describe("buildMonthGrid", () => {
  it("Monday-start month with no padding (Feb 2021 starts Monday)", () => {
    const cells = buildMonthGrid(2021, 1); // month is 0-indexed -> Feb
    expect(cells.length).toBe(28);
    expect(cells[0]).toEqual({ dateStr: "2021-02-01", dayNum: 1, inMonth: true });
    expect(cells[27]).toEqual({ dateStr: "2021-02-28", dayNum: 28, inMonth: true });
    expect(cells.filter((c) => c.inMonth).length).toBe(28);
  });

  it("pads leading + trailing to full weeks (Aug 2021 starts Sunday)", () => {
    const cells = buildMonthGrid(2021, 7); // Aug
    expect(cells.length % 7).toBe(0);
    expect(cells.length).toBe(42);
    expect(cells[0]).toEqual({ dateStr: "2021-07-26", dayNum: 26, inMonth: false });
    const firstInMonth = cells.find((c) => c.inMonth)!;
    expect(firstInMonth.dateStr).toBe("2021-08-01");
    expect(cells.filter((c) => c.inMonth).length).toBe(31);
    expect(cells[cells.length - 1].inMonth).toBe(false);
  });

  it("leading padding crosses the year boundary (Jan 2021 leads from Dec 2020)", () => {
    const cells = buildMonthGrid(2021, 0); // Jan 2021, the 1st is a Friday
    const firstInMonthIdx = cells.findIndex((c) => c.inMonth);
    expect(firstInMonthIdx).toBe(4); // Mon..Thu from December
    expect(cells.slice(0, firstInMonthIdx).every((c) => c.dateStr.startsWith("2020-12"))).toBe(true);
    expect(cells[0].dateStr).toBe("2020-12-28");
  });
});
