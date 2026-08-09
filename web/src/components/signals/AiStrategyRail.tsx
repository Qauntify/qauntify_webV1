"use client";

import { SlidingPillNav } from "@/components/shared/SlidingPillNav";
import {
  AI_SIGNAL_STRATEGY_OPTIONS,
  type AiSignalStrategy,
} from "@/lib/signals-browse-tabs";

/** Sub-filter nested inside the AI Signal tab — pick a strategy, or all of them. */
export function AiStrategyRail({
  strategy,
  basePath,
}: {
  strategy: AiSignalStrategy;
  basePath: string;
}) {
  return (
    <SlidingPillNav
      ariaLabel="យុទ្ធសាស្ត្រ AI"
      activeId={strategy}
      options={AI_SIGNAL_STRATEGY_OPTIONS}
      hrefFor={(id) =>
        id === "all" ? `${basePath}?tab=ai` : `${basePath}?tab=ai&strategy=${id}`
      }
      size="sm"
    />
  );
}
