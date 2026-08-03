"use client";

import Image from "next/image";
import { useEffect, useId, useState } from "react";

import { SectionHeader } from "@/components/shared/SectionHeader";

type Certificate = {
  id: string;
  src: string;
  title: string;
  issuer: string;
  kind: "image" | "pdf";
};

const CERTIFICATES: Certificate[] = [
  {
    id: "hola-phase1-jun2",
    src: "/certificate/certificate 1.jpeg",
    title: "Phase 1 passed",
    issuer: "Hola Prime",
    kind: "image",
  },
  {
    id: "hola-phase1-jun8",
    src: "/certificate/certificate 2.jpeg",
    title: "Phase 1 passed",
    issuer: "Hola Prime",
    kind: "image",
  },
  {
    id: "hola-phase1-jun16",
    src: "/certificate/certificate 3.jpeg",
    title: "Phase 1 passed",
    issuer: "Hola Prime",
    kind: "image",
  },
  {
    id: "hola-phase1-4",
    src: "/certificate/certificate 4.jpeg",
    title: "Challenge certificate",
    issuer: "Hola Prime",
    kind: "image",
  },
  {
    id: "hola-funded",
    src: "/certificate/certificate 5.jpeg",
    title: "Funded trader",
    issuer: "Hola Prime",
    kind: "image",
  },
  {
    id: "alpha-futures",
    src: "/certificate/Alpha_Future_Eval_Certificate.png",
    title: "Evaluation passed",
    issuer: "Alpha Futures",
    kind: "image",
  },
  {
    id: "fundednext-crown-v1",
    src: "/certificate/Funded_Crown_v1.jpg",
    title: "Crown Trader",
    issuer: "FundedNext",
    kind: "image",
  },
  {
    id: "fundednext-crown-v3",
    src: "/certificate/Fundednext_Crown_v3.jpg",
    title: "Crown Trader",
    issuer: "FundedNext",
    kind: "image",
  },
  {
    id: "virakyuth-pdf",
    src: "/certificate/Certificate for  Virakyuth Srun.pdf",
    title: "Certificate of completion",
    issuer: "Virakyuth Srun",
    kind: "pdf",
  },
];

export function Certificates() {
  const titleId = useId();
  const [active, setActive] = useState<Certificate | null>(null);

  useEffect(() => {
    if (!active) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setActive(null);
    };
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [active]);

  const renderCard = (cert: Certificate, interactive: boolean) =>
    cert.kind === "pdf" ? (
      <a
        href={cert.src}
        target="_blank"
        rel="noopener noreferrer"
        tabIndex={interactive ? undefined : -1}
        className="cert-card flex h-full w-[240px] flex-col justify-between sm:w-[280px]"
      >
        <div>
          <p className="text-xs font-medium uppercase tracking-wider text-accent">
            PDF
          </p>
          <p className="mt-3 text-base font-semibold text-ink">{cert.title}</p>
          <p className="mt-1 text-sm text-slate">{cert.issuer}</p>
        </div>
        <p className="mt-6 text-sm font-medium text-accent">Open certificate</p>
      </a>
    ) : (
      <button
        type="button"
        onClick={interactive ? () => setActive(cert) : undefined}
        tabIndex={interactive ? undefined : -1}
        className="cert-card group w-[240px] text-left sm:w-[280px]"
        aria-label={`View ${cert.issuer} — ${cert.title}`}
      >
        <div className="relative aspect-[4/3] overflow-hidden rounded-md bg-line/40">
          <Image
            src={cert.src}
            alt={`${cert.issuer}: ${cert.title}`}
            fill
            sizes="280px"
            className="object-cover transition duration-300 group-hover:scale-[1.03]"
          />
        </div>
        <div className="mt-3">
          <p className="text-sm font-semibold text-ink">{cert.issuer}</p>
          <p className="mt-0.5 text-xs text-slate">{cert.title}</p>
        </div>
      </button>
    );

  const track = (
    <div className="cert-marquee-track">
      {[0, 1].map((copy) => (
        <ul
          key={copy}
          className="flex shrink-0 items-stretch gap-4 pr-4"
          aria-hidden={copy === 1}
        >
          {CERTIFICATES.map((cert) => (
            <li key={`${copy}-${cert.id}`} className="shrink-0">
              {renderCard(cert, copy === 0)}
            </li>
          ))}
        </ul>
      ))}
    </div>
  );

  return (
    <section id="proof" className="section-block overflow-hidden bg-card/40">
      <div className="page-container py-16 md:py-20">
        <SectionHeader
          eyebrow="Proof"
          title="Verified certificates. Real props passed."        
        />
      </div>

      <div className="cert-marquee pb-16 md:pb-20" role="region" aria-label="Certificates">
        {track}
      </div>

      {active && active.kind === "image" ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-ink/70 p-4 backdrop-blur-sm"
          role="dialog"
          aria-modal="true"
          aria-labelledby={titleId}
          onClick={() => setActive(null)}
        >
          <div
            className="relative max-h-[90vh] w-full max-w-4xl overflow-hidden rounded-lg bg-card shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between gap-4 border-b border-line px-4 py-3">
              <div>
                <p id={titleId} className="font-semibold text-ink">
                  {active.issuer}
                </p>
                <p className="text-sm text-slate">{active.title}</p>
              </div>
              <button
                type="button"
                onClick={() => setActive(null)}
                className="btn-secondary px-3 py-1.5 text-sm"
              >
                Close
              </button>
            </div>
            <div className="relative aspect-[4/3] w-full bg-line/30">
              <Image
                src={active.src}
                alt={`${active.issuer}: ${active.title}`}
                fill
                sizes="896px"
                className="object-contain"
                priority
              />
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}
