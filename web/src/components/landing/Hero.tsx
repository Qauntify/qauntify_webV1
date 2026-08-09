import Link from "next/link";

import { HeroAmbient } from "@/components/landing/HeroAmbient";
import { HowAiWorks } from "@/components/landing/HowAiWorks";
import type { Stats } from "@/lib/signals";

/** Paste the public Telegram group invite here. */
const TELEGRAM_GROUP_URL = "https://t.me/quantify_chat";

export function Hero({ stats }: { stats: Stats }) {
  return (
    <section className="hero-ambient flex min-h-[calc(100dvh-4rem)] flex-col border-b border-line">
      <HeroAmbient />

      <div className="page-container relative z-10 grid flex-1 items-center gap-6 py-6 md:grid-cols-[1fr_1.05fr] md:gap-8 md:py-8 lg:grid-cols-[1fr_0.95fr]">
        <div className="flex flex-col">
          <div className="flex flex-wrap items-center gap-2">
            <p className="font-mono text-[11px] font-semibold uppercase tracking-[0.18em] text-ink">
              Qauntify
            </p>
            <span className="rounded-full bg-long-soft px-2 py-0.5 font-mono text-[10px] font-bold uppercase tracking-wide text-long">
              ឥតគិតថ្លៃ · បើកចំហ · តម្លាភាព
            </span>
          </div>
          <h1 className="mt-2 text-[1.85rem] font-extrabold leading-[1.2] tracking-tight text-ink sm:text-4xl lg:text-[2.5rem]">
            បង្កើតឡើងដោយសហគមន៍
            <span className="block text-slate">
              Trade រួមគ្នា រៀនរួមគ្នា រីកចម្រើនរួមគ្នា
            </span>
          </h1>
          <p className="mt-3 max-w-md text-sm leading-relaxed text-slate">
            Trading signals ត្រូវបានវិភាគតាមច្បាប់ដែលបានកំណត់យ៉ាងច្បាស់ ហើយ AI
            ជួយពិនិត្យ និងបញ្ជាក់ការរៀបចំទីផ្សារ។ រាល់ចំណុចចូល បញ្ឈប់ខាត គោលដៅ
            និងហេតុផល ត្រូវបានកត់ត្រាទុក ដើម្បីឱ្យសហគមន៍អាចតាមដាន និងពិនិត្យលទ្ធផល
            រួចកែរសម្រួលទាំងអស់គ្នា។
          </p>
          <div className="mt-5 flex flex-wrap items-center gap-2.5">
            <Link href="/signals" className="btn-primary">
              មើល Signals
            </Link>
            <Link href="/track-record" className="btn-secondary">
              មើលកំណត់ត្រាលទ្ធផល
            </Link>
            <Link
              href="/war-room"
              className="px-2 text-sm font-semibold text-slate hover:text-ink"
            >
              ចូល War Room →
            </Link>
          </div>

          <a
            href={TELEGRAM_GROUP_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-5 flex max-w-md items-start gap-3 rounded-lg border border-line bg-card px-3.5 py-3 transition-colors hover:border-ink/25"
          >
            <span
              className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[#229ED9]/15 text-[#229ED9]"
              aria-hidden
            >
              <TelegramIcon />
            </span>
            <span className="min-w-0">
              <span className="block text-sm font-semibold text-ink">
                ចូលក្រុម Telegram រួមគ្នា
              </span>
              <span className="mt-0.5 block text-[13px] leading-relaxed text-slate">
                ផ្តល់មតិយោបល់ ផ្តល់គំនិត ជួយកែប្រែ និងរីកចម្រើនជាមួយគ្នា — ទទួល
                signals លឿនផងដែរ។ ចុចដើម្បីចូលក្រុម →
              </span>
            </span>
          </a>
        </div>

        <HowAiWorks stats={stats} />
      </div>
    </section>
  );
}

function TelegramIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
      <path d="M11.944 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0a12 12 0 0 0-.056 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.48.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.788.027-.216.325-.437.893-.663 3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z" />
    </svg>
  );
}
