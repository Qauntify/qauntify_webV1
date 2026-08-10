import Link from "next/link";

import { Logo } from "@/components/shared/Logo";
import { ThemeToggle } from "@/components/shared/ThemeToggle";
import { SHOW_LOGIN_LINK } from "@/lib/access-mode";
import { isAdminEmail } from "@/lib/supabase/admin";
import { createClient } from "@/lib/supabase/server";

const links = [
  { href: "/signals", label: "Signals" },
  { href: "/war-room", label: "War Room" },
  { href: "/track-record", label: "កំណត់ត្រាលទ្ធផល" },
  { href: "/tools", label: "ឧបករណ៍" },
];

export async function Nav() {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  const email = user?.email ?? null;

  return (
    <div className="sticky top-0 z-40">
      <div
        className="warn-marquee border-b border-amber-600/40 bg-amber-500/10 py-2"
        role="region"
        aria-label="ការព្រមានអំពីហានិភ័យ"
      >
        <div className="warn-marquee-track">
          {[0, 1].map((copy) => (
            <span
              key={copy}
              className="flex shrink-0 items-center gap-1.5 pr-10 text-[11px] font-medium whitespace-nowrap text-amber-700 dark:text-amber-400 sm:text-xs"
              aria-hidden={copy === 1}
            >
              <span aria-hidden>⚠</span>
              Qauntify កំពុងអភិវឌ្ឍន៍យ៉ាងសកម្ម។ Signals ត្រូវបានចែករំលែកសម្រាប់
              គោលបំណងអប់រំ និងស្រាវជ្រាវតែប៉ុណ្ណោះ — នេះមិនមែនជា
              ដំបូន្មានហិរញ្ញវត្ថុទេ ហើយការជួញដូរមានហានិភ័យនៃការខាតបង់។
            </span>
          ))}
        </div>
      </div>
      <header className="border-b border-line bg-card">
        <div className="page-container flex h-16 items-center justify-between">
          <Logo />
          <nav className="hidden items-center gap-8 text-sm font-medium text-slate md:flex">
            {links.map((l) => (
              <Link key={l.href} href={l.href} className="hover:text-ink">
                {l.label}
              </Link>
            ))}
          </nav>
          <div className="flex items-center gap-2">
            <ThemeToggle />
            {email && isAdminEmail(email) ? (
              <Link href="/admin" className="btn-secondary py-2! px-4! text-sm!">
                Admin
              </Link>
            ) : null}
            {!email && SHOW_LOGIN_LINK ? (
              <Link href="/login" className="btn-primary-sm">
                ចូលគណនី
              </Link>
            ) : null}
          </div>
        </div>
      </header>
    </div>
  );
}
