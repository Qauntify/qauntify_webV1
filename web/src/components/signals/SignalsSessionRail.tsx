"use client";

import { SlidingPillNav } from "@/components/shared/SlidingPillNav";
import {
  SIGNAL_FILTER_OPTIONS,
  type SignalFilterOption,
  type SignalsBrowseTab,
} from "@/lib/signals-browse-tabs";

/** Top-level session filter — a sliding-pill segmented control. */
export function SignalsSessionRail({
  tab,
  basePath,
  options = SIGNAL_FILTER_OPTIONS,
}: {
  tab: SignalsBrowseTab | string;
  basePath: string;
  options?: SignalFilterOption[];
}) {
  return (
    <SlidingPillNav
      ariaLabel="Sessions"
      activeId={tab}
      options={options}
      hrefFor={(id) => (id === "all" ? basePath : `${basePath}?tab=${id}`)}
    />
  );
}
