"use client";

import Image from "next/image";
import { useEffect, useId, useState } from "react";

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
    title: "បានជាប់ដំណាក់កាលទី 1",
    issuer: "Hola Prime",
    kind: "image",
  },
  {
    id: "hola-phase1-jun8",
    src: "/certificate/certificate 2.jpeg",
    title: "បានជាប់ដំណាក់កាលទី 1",
    issuer: "Hola Prime",
    kind: "image",
  },
  {
    id: "hola-phase1-jun16",
    src: "/certificate/certificate 3.jpeg",
    title: "បានជាប់ដំណាក់កាលទី 1",
    issuer: "Hola Prime",
    kind: "image",
  },
  {
    id: "hola-phase1-4",
    src: "/certificate/certificate 4.jpeg",
    title: "វិញ្ញាបនបត្រប្រកួតប្រជែង",
    issuer: "Hola Prime",
    kind: "image",
  },
  {
    id: "hola-funded",
    src: "/certificate/certificate 5.jpeg",
    title: "អ្នកជួញដូរដែលទទួលមូលនិធិ",
    issuer: "Hola Prime",
    kind: "image",
  },
  {
    id: "alpha-futures",
    src: "/certificate/Alpha_Future_Eval_Certificate.png",
    title: "បានជាប់ការវាយតម្លៃ",
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
    title: "វិញ្ញាបនបត្របញ្ចប់",
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
        className="flex h-full w-[180px] flex-col justify-between rounded-md border border-line bg-card p-3 sm:w-[200px]"
      >
        <div>
          <p className="font-mono text-[10px] font-semibold uppercase tracking-wider text-ink">
            PDF
          </p>
          <p className="mt-1.5 text-sm font-semibold text-ink">{cert.title}</p>
          <p className="mt-0.5 text-xs text-slate">{cert.issuer}</p>
        </div>
        <p className="mt-3 text-xs font-semibold text-ink">បើក →</p>
      </a>
    ) : (
      <button
        type="button"
        onClick={interactive ? () => setActive(cert) : undefined}
        tabIndex={interactive ? undefined : -1}
        className="w-[180px] rounded-md border border-line bg-card p-1.5 text-left transition-colors hover:border-ink/30 sm:w-[200px]"
        aria-label={`មើល ${cert.issuer} — ${cert.title}`}
      >
        <div className="relative aspect-[4/3] overflow-hidden rounded bg-line">
          <Image
            src={cert.src}
            alt={`${cert.issuer}: ${cert.title}`}
            fill
            sizes="200px"
            className="object-cover"
          />
        </div>
        <div className="mt-1.5 px-1 pb-0.5">
          <p className="text-sm font-semibold text-ink">{cert.issuer}</p>
          <p className="text-xs text-slate">{cert.title}</p>
        </div>
      </button>
    );

  const track = (
    <div className="cert-marquee-track">
      {[0, 1].map((copy) => (
        <ul
          key={copy}
          className="flex shrink-0 items-stretch gap-2.5 pr-2.5"
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
    <section id="proof" className="overflow-hidden border-b border-line bg-paper">
      <div className="page-container flex items-end justify-between gap-4 py-10 md:py-14">
        <div>
          <p className="font-mono text-[11px] font-semibold uppercase tracking-[0.14em] text-ink">
            ភស្តុតាង
          </p>
          <h2 className="mt-1 text-xl font-bold tracking-tight text-ink md:text-2xl">
            វិញ្ញាបនបត្រ Prop។ ជាប់ពិតៗ។
          </h2>
        </div>
        <p className="hidden max-w-xs text-right text-xs text-slate sm:block">
          វិញ្ញាបនបត្រមូលនិធិ និងការវាយតម្លៃពីការប្រកួតប្រជែង prop ផ្ទាល់។
        </p>
      </div>

      <div className="cert-marquee pb-5 md:pb-6" role="region" aria-label="វិញ្ញាបនបត្រ">
        {track}
      </div>

      {active && active.kind === "image" ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby={titleId}
          onClick={() => setActive(null)}
        >
          <div
            className="relative max-h-[90vh] w-full max-w-4xl overflow-hidden rounded-lg border border-line bg-card shadow-xl"
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
                បិទ
              </button>
            </div>
            <div className="relative aspect-[4/3] w-full bg-paper">
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
