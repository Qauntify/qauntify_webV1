"use client";

import { useEffect, useId, useRef, useState } from "react";

type ExportTab = "all" | "super-scalping" | "scalping" | "swing";

export function ExportSignalsMenu({
  tab,
  disabled,
}: {
  tab: ExportTab;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const menuId = useId();

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

  function href(format: "xlsx" | "pdf") {
    const params = new URLSearchParams({ format });
    if (tab !== "all") params.set("tab", tab);
    return `/api/admin/signals/export?${params.toString()}`;
  }

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        disabled={disabled}
        aria-expanded={open}
        aria-haspopup="menu"
        aria-controls={menuId}
        title={
          disabled
            ? "No TP/SL-hit signals for this filter"
            : "Download closed TP/SL signals"
        }
        onClick={() => setOpen((v) => !v)}
        className="btn-secondary disabled:opacity-40 disabled:cursor-not-allowed"
      >
        Export
        <svg
          className="ml-1.5 h-3.5 w-3.5 text-slate"
          viewBox="0 0 20 20"
          fill="currentColor"
          aria-hidden
        >
          {open ? (
            <path d="M14.77 12.79a.75.75 0 0 1-1.06-.02L10 8.832 6.29 12.77a.75.75 0 1 1-1.08-1.04l4.25-4.5a.75.75 0 0 1 1.08 0l4.25 4.5a.75.75 0 0 1-.02 1.06z" />
          ) : (
            <path d="M5.23 7.21a.75.75 0 0 1 1.06.02L10 11.168l3.71-3.938a.75.75 0 1 1 1.08 1.04l-4.25 4.5a.75.75 0 0 1-1.08 0l-4.25-4.5a.75.75 0 0 1 .02-1.06z" />
          )}
        </svg>
      </button>

      {open && !disabled ? (
        <div
          id={menuId}
          role="menu"
          className="absolute right-0 z-20 mt-2 min-w-[10rem] overflow-hidden rounded-lg border border-line bg-card shadow-lg"
        >
          <a
            role="menuitem"
            href={href("xlsx")}
            className="block px-4 py-2.5 text-sm font-medium text-ink hover:bg-accent-soft"
            onClick={() => setOpen(false)}
          >
            Excel (.xlsx)
          </a>
          <a
            role="menuitem"
            href={href("pdf")}
            className="block border-t border-line px-4 py-2.5 text-sm font-medium text-ink hover:bg-accent-soft"
            onClick={() => setOpen(false)}
          >
            PDF (.pdf)
          </a>
        </div>
      ) : null}
    </div>
  );
}
