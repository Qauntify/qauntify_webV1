"use client";

import Link from "next/link";
import { useEffect, useId, useRef, useState } from "react";

import {
  SIGNAL_FILTER_OPTIONS,
  type SignalFilterOption,
} from "@/lib/signals-browse-tabs";

export type {
  SignalFilterOption,
  SignalsBrowseTab,
} from "@/lib/signals-browse-tabs";
export {
  ADMIN_SIGNAL_FILTER_OPTIONS,
  parseSignalsBrowseTab,
  SIGNAL_FILTER_OPTIONS,
} from "@/lib/signals-browse-tabs";

/** Custom session filter — same pattern as ExportSignalsMenu (no native select). */
export function SignalsBrowseFilter({
  tab,
  basePath,
  options = SIGNAL_FILTER_OPTIONS,
  label = "Session",
  showLabel = true,
  compact = false,
}: {
  tab: string;
  basePath: string;
  options?: SignalFilterOption[];
  label?: string;
  /** When false, label is screen-reader only (for header rows). */
  showLabel?: boolean;
  /** Single-line trigger — better in tight header rows. */
  compact?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const menuId = useId();
  const current = options.find((o) => o.id === tab) ?? options[0];

  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: MouseEvent) {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  function hrefFor(id: string) {
    return id === "all" ? basePath : `${basePath}?tab=${id}`;
  }

  return (
    <div ref={rootRef} className="relative w-full min-w-[11rem] max-w-xs sm:w-56">
      {showLabel ? (
        <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-wider text-slate/70">
          {label}
        </label>
      ) : (
        <span className="sr-only">{label}</span>
      )}
      <button
        type="button"
        aria-expanded={open}
        aria-haspopup="listbox"
        aria-controls={menuId}
        aria-label={label}
        onClick={() => setOpen((v) => !v)}
        className="btn-secondary flex w-full items-center justify-between gap-3 text-left"
      >
        <span className="min-w-0">
          <span className="block truncate text-sm font-semibold text-ink">
            {current.label}
          </span>
          {!compact ? (
            <span className="block truncate text-[11px] font-medium text-slate">
              {current.hint}
            </span>
          ) : null}
        </span>
        <svg
          className={`h-4 w-4 shrink-0 text-slate transition-transform ${
            open ? "rotate-180" : ""
          }`}
          viewBox="0 0 20 20"
          fill="currentColor"
          aria-hidden
        >
          <path d="M5.23 7.21a.75.75 0 0 1 1.06.02L10 11.168l3.71-3.938a.75.75 0 1 1 1.08 1.04l-4.25 4.5a.75.75 0 0 1-1.08 0l-4.25-4.5a.75.75 0 0 1 .02-1.06z" />
        </svg>
      </button>

      {open ? (
        <ul
          id={menuId}
          role="listbox"
          aria-label={label}
          className="absolute left-0 z-30 mt-2 w-full overflow-hidden rounded-lg border border-line bg-card shadow-[var(--shadow-card-hover)]"
        >
          {options.map((opt, index) => {
            const active = opt.id === tab;
            return (
              <li key={opt.id} role="option" aria-selected={active}>
                <Link
                  href={hrefFor(opt.id)}
                  onClick={() => setOpen(false)}
                  className={`block px-4 py-2.5 transition-colors ${
                    active
                      ? "bg-ink text-paper"
                      : "text-ink hover:bg-accent-soft"
                  } ${index > 0 ? "border-t border-line" : ""}`}
                >
                  <span className="block text-sm font-semibold">{opt.label}</span>
                  <span
                    className={`block text-[11px] ${
                      active ? "text-paper/70" : "text-slate"
                    }`}
                  >
                    {opt.hint}
                  </span>
                </Link>
              </li>
            );
          })}
        </ul>
      ) : null}
    </div>
  );
}
