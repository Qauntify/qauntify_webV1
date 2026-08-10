import { describe, expect, it } from "vitest";

import { buildChartAnnotations } from "@/lib/mt5-signal";

describe("buildChartAnnotations", () => {
  it("maps FVG + sweep + CHoCH and converts ms times to seconds", () => {
    const out = buildChartAnnotations({
      fvg_top: 2652.5,
      fvg_bottom: 2650.1,
      fvg_start_time: 1_723_000_000_000,
      sweep_level: 2648,
      sweep_time: 1_723_000_060_000,
      choch_level: 2651,
      choch_time: 1_723_000_120_000,
    });
    expect(out.fvg_top).toBe(2652.5);
    expect(out.fvg_bottom).toBe(2650.1);
    expect(out.fvg_start).toBe(1_723_000_000);
    expect(out.sweep_time).toBe(1_723_000_060);
    expect(out.choch_level).toBe(2651);
  });

  it("returns empty for missing indicators", () => {
    expect(buildChartAnnotations(null)).toEqual({});
    expect(buildChartAnnotations({})).toEqual({});
  });
});
