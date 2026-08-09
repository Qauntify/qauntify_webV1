"use client";

import Image from "next/image";
import { useEffect, useId, useState } from "react";

const PROOF_SRC = "/proof_strategy_testing/strategy_testing.png";
const PROOF_ALT =
  "ផែនទីកម្ដៅសាកល្បងយុទ្ធសាស្ត្រប្រចាំខែពីឆ្នាំ 2020 ដល់ 2026 បង្ហាញប្រាក់ចំណេញ ការខាត និងចំនួនការជួញដូរក្នុងមួយខែ";

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
    <section id="strategy-testing" className="border-b border-line bg-card">
      <div className="page-container py-10 md:py-14">
        <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
          <div>
            <p className="font-mono text-[11px] font-semibold uppercase tracking-[0.14em] text-ink">
              សាកល្បងយុទ្ធសាស្ត្រ
            </p>
            <h2 className="mt-1 text-xl font-bold tracking-tight text-ink md:text-2xl">
              លទ្ធផលប្រចាំខែ 2020–2026
            </h2>
          </div>
          <p className="text-xs font-medium text-slate">ចុចដើម្បីពង្រីក</p>
        </div>

        <button
          type="button"
          onClick={() => setOpen(true)}
          className="group w-full overflow-hidden rounded-lg border border-line bg-paper p-1 text-left transition-colors hover:border-ink/30"
          aria-label="ពង្រីកផែនទីកម្ដៅសាកល្បងយុទ្ធសាស្ត្រ"
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
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-2 sm:p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby={titleId}
          onClick={() => setOpen(false)}
        >
          <div
            className="relative flex max-h-[96vh] w-full max-w-[98vw] flex-col overflow-hidden rounded-lg border border-line bg-card shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex shrink-0 items-center justify-between gap-4 border-b border-line px-4 py-3">
              <div>
                <p id={titleId} className="font-semibold text-ink">
                  សាកល្បងយុទ្ធសាស្ត្រ
                </p>
                <p className="text-sm text-slate">ផែនទីកម្ដៅលទ្ធផលប្រចាំខែ</p>
              </div>
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="btn-secondary px-3 py-1.5 text-sm"
              >
                បិទ
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
