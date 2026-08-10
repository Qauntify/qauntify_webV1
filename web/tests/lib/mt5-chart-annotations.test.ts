import { describe, expect, it } from "vitest";

import { buildChartAnnotations } from "@/lib/mt5-signal";

describe("buildChartAnnotations", () => {
  it("maps FVG + sweep + CHoCH and converts ms times to seconds", () => {
    const out = buildChartAnnotations({
      fvg_top: 2652.5,
      fvg_bottom: 2650.1,
      fvg_start_time: 1_723_000_000_000,
      fvg_end_time: 1_723_000_180_000,
      sweep_level: 2648,
      sweep_time: 1_723_000_060_000,
      choch_level: 2651,
      choch_time: 1_723_000_120_000,
    });
    expect(out.fvg_top).toBe(2652.5);
    expect(out.fvg_bottom).toBe(2650.1);
    expect(out.fvg_start).toBe(1_723_000_000);
    expect(out.fvg_end).toBe(1_723_000_180);
    expect(out.sweep_time).toBe(1_723_000_060);
    expect(out.choch_level).toBe(2651);
  });

  it("falls back fvg_end from periodMinutes when missing", () => {
    const out = buildChartAnnotations(
      { fvg_top: 1, fvg_bottom: 0.5, fvg_start_time: 1_700_000_000 },
      { periodMinutes: 1 },
    );
    expect(out.fvg_start).toBe(1_700_000_000);
    expect(out.fvg_end).toBe(1_700_000_000 + 180);
  });

  it("passes cloud CSV series through as strings", () => {
    const out = buildChartAnnotations({
      cloud_t: "100,160,220",
      cloud_lo: "2640.1,2641.2,2642.3",
      cloud_hi: "2650.1,2651.2,2652.3",
      cloud_high: 2652.3,
      cloud_low: 2642.3,
    });
    expect(out.cloud_t).toBe("100,160,220");
    expect(out.cloud_lo).toBe("2640.1,2641.2,2642.3");
    expect(out.cloud_hi).toBe("2650.1,2651.2,2652.3");
    expect(out.cloud_high).toBe(2652.3);
  });

  it("returns empty for missing indicators", () => {
    expect(buildChartAnnotations(null)).toEqual({});
    expect(buildChartAnnotations({})).toEqual({});
  });
});
