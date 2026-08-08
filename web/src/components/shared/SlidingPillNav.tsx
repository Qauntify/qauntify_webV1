"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

export type PillNavOption = {
  id: string;
  label: string;
  disabled?: boolean;
};

/** Segmented nav with a single pill that glides to the active tab, in the
 * style Linear/Vercel use for plan/session switchers — measures the active
 * link's position via DOM refs rather than toggling per-tab backgrounds. */
export function SlidingPillNav({
  options,
  activeId,
  hrefFor,
  ariaLabel,
  size = "md",
}: {
  options: PillNavOption[];
  activeId: string;
  hrefFor: (id: string) => string;
  ariaLabel: string;
  size?: "md" | "sm";
}) {
  const trackRef = useRef<HTMLDivElement>(null);
  const itemRefs = useRef<Record<string, HTMLAnchorElement | null>>({});
  const [pill, setPill] = useState<{ left: number; width: number } | null>(null);

  useEffect(() => {
    const el = itemRefs.current[activeId];
    const track = trackRef.current;
    if (!el || !track) {
      setPill(null);
      return;
    }
    const update = () => {
      const trackRect = track.getBoundingClientRect();
      const elRect = el.getBoundingClientRect();
      setPill({ left: elRect.left - trackRect.left, width: elRect.width });
    };
    update();
    window.addEventListener("resize", update);
    return () => window.removeEventListener("resize", update);
  }, [activeId, options]);

  const padY = size === "sm" ? "py-1.5" : "py-2.5";

  return (
    <nav
      aria-label={ariaLabel}
      ref={trackRef}
      className="relative flex w-full gap-1 overflow-x-auto rounded-full border border-line bg-paper p-1 [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
    >
      {pill ? (
        <span
          aria-hidden
          className="pointer-events-none absolute top-1 bottom-1 rounded-full bg-ink transition-[transform,width] duration-300 ease-out"
          style={{ transform: `translateX(${pill.left}px)`, width: `${pill.width}px` }}
        />
      ) : null}
      {options.map((opt) => {
        if (opt.disabled) {
          return (
            <span
              key={opt.id}
              title="Coming soon"
              aria-disabled="true"
              className={`relative z-10 flex shrink-0 cursor-not-allowed items-center whitespace-nowrap rounded-full px-4 ${padY} text-xs font-semibold text-slate opacity-40`}
            >
              {opt.label}
            </span>
          );
        }
        const active = opt.id === activeId;
        return (
          <Link
            key={opt.id}
            ref={(node) => {
              itemRefs.current[opt.id] = node;
            }}
            href={hrefFor(opt.id)}
            aria-current={active ? "page" : undefined}
            className={`relative z-10 flex shrink-0 items-center whitespace-nowrap rounded-full px-4 ${padY} text-xs font-semibold transition-colors duration-300 ${
              active ? "text-card" : "text-slate hover:text-ink"
            }`}
          >
            {opt.label}
          </Link>
        );
      })}
    </nav>
  );
}
