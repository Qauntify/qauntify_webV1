"use client";

import Image from "next/image";
import { useEffect, useId, useState } from "react";

const PROOF_SRC = "/proof_strategy_testing/strategy_testing.png";
const PROOF_ALT =
  "Monthly strategy testing heatmap from 2020 to 2026 showing profit, loss, and trade counts per month";

export function StrategyTesting() {
  const titleId = useId();
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [open]);

  return (
    <section id="strategy-testing" className="border-b border-line bg-[#fff]">
      <div className="page-container py-5 md:py-6">
        <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
          <div>
            <p className="font-mono text-[11px] font-semibold uppercase tracking-[0.14em] text-ink">
              Strategy testing
            </p>
            <h2 className="mt-1 text-xl font-bold tracking-tight text-ink md:text-2xl">
              Monthly results, 2020–2026
            </h2>
          </div>
          <p className="text-xs font-medium text-slate">Click to enlarge</p>
        </div>

        <button
          type="button"
          onClick={() => setOpen(true)}
          className="group w-full overflow-hidden rounded-lg border border-line bg-[#f1f5f9] p-1 text-left transition-colors hover:border-ink/30"
          aria-label="Enlarge strategy testing heatmap"
        >
          <div className="relative aspect-[2814/1372] w-full overflow-hidden rounded-md bg-ink">
            <Image
              src={PROOF_SRC}
              alt={PROOF_ALT}
              fill
              sizes="(max-width: 768px) 100vw, 72rem"
              className="object-contain"
              priority={false}
            />
          </div>
        </button>
      </div>

      {open ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-ink/80 p-2 sm:p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby={titleId}
          onClick={() => setOpen(false)}
        >
          <div
            className="relative flex max-h-[96vh] w-full max-w-[98vw] flex-col overflow-hidden rounded-lg border border-line bg-white shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex shrink-0 items-center justify-between gap-4 border-b border-line px-4 py-3">
              <div>
                <p id={titleId} className="font-semibold text-ink">
                  Strategy testing
                </p>
                <p className="text-sm text-slate">Monthly performance heatmap</p>
              </div>
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="btn-secondary px-3 py-1.5 text-sm"
              >
                Close
              </button>
            </div>
            <div className="relative min-h-0 flex-1 overflow-auto bg-ink p-2 sm:p-3">
              <Image
                src={PROOF_SRC}
                alt={PROOF_ALT}
                width={2814}
                height={1372}
                sizes="98vw"
                className="mx-auto h-auto w-full max-w-none"
                priority
              />
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}
