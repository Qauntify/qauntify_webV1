"use client";

import Image from "next/image";
import { useEffect, useId, useState } from "react";

import { SectionHeader } from "@/components/shared/SectionHeader";

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
    <section id="strategy-testing" className="section-block">
      <div className="page-container py-16 pb-8 md:py-20 md:pb-10">
        <SectionHeader
          eyebrow="Strategy testing"
          title="Monthly results across years of live-style replay."          
        />
      </div>

      <div className="mx-auto w-full max-w-[96rem] px-3 pb-16 sm:px-4 md:px-6 md:pb-20">
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="cert-card group w-full overflow-hidden p-1.5 text-left sm:p-2"
          aria-label="Enlarge strategy testing heatmap"
        >
          <div className="relative aspect-[2814/1372] min-h-[280px] w-full overflow-hidden rounded-md bg-[#0d0d0d] sm:min-h-[420px] lg:min-h-[520px] xl:min-h-[620px]">
            <Image
              src={PROOF_SRC}
              alt={PROOF_ALT}
              fill
              sizes="(max-width: 768px) 100vw, (max-width: 1536px) 96rem, 1536px"
              className="object-contain transition duration-300 group-hover:scale-[1.01]"
              priority={false}
            />
          </div>
          <p className="mt-3 px-1 text-xs text-slate sm:text-sm">
            Click to enlarge — monthly P&amp;L heatmap, 2020–2026
          </p>
        </button>
      </div>

      {open ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-ink/80 p-2 backdrop-blur-sm sm:p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby={titleId}
          onClick={() => setOpen(false)}
        >
          <div
            className="relative flex max-h-[96vh] w-full max-w-[98vw] flex-col overflow-hidden rounded-lg bg-card shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex shrink-0 items-center justify-between gap-4 border-b border-line bg-card px-4 py-3">
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
            <div className="relative min-h-0 flex-1 overflow-auto bg-[#0d0d0d] p-2 sm:p-3">
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
