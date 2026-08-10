import Link from "next/link";
import type { Metadata } from "next";

import { Footer } from "@/components/shared/Footer";
import { Nav } from "@/components/shared/Nav";

export const metadata: Metadata = {
  title: "រកមិនឃើញទំព័រ — Qauntify",
  description: "ទំព័រដែលបងប្អូនស្វែងរកមិនមានទេ។",
};

export default function NotFound() {
  return (
    <>
      <Nav />
      <main className="flex min-h-[calc(100svh-4rem)] flex-1 flex-col bg-paper">
        <div className="page-container flex flex-1 flex-col items-center justify-center py-16 text-center">
          <p className="font-mono text-xs font-semibold uppercase tracking-[0.2em] text-slate">
            404
          </p>
          <h1 className="mt-3 text-3xl font-extrabold tracking-tight text-ink sm:text-4xl">
            រកមិនឃើញទំព័រ
          </h1>
          <p className="mt-3 max-w-md text-base leading-relaxed text-slate">
            ទំព័រដែលបងប្អូនស្វែងរកមិនមាន ឬត្រូវបានផ្លាស់ទី។ សូមត្រឡប់ទៅទំព័រដើម
            ឬមើល Signals បន្ត។
          </p>
          <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
            <Link href="/" className="btn-primary">
              ទៅទំព័រដើម
            </Link>
            <Link href="/signals" className="btn-secondary">
              មើល Signals
            </Link>
            <Link href="/tools" className="btn-ghost text-sm font-semibold text-slate hover:text-ink">
              ឧបករណ៍
            </Link>
          </div>
        </div>
      </main>
      <Footer />
    </>
  );
}
