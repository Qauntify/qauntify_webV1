import Link from "next/link";

import { Logo } from "@/components/shared/Logo";
import { ThemeToggle } from "@/components/shared/ThemeToggle";
import { isAdminEmail } from "@/lib/supabase/admin";
import { createClient } from "@/lib/supabase/server";

const links = [
  { href: "/#features", label: "Features" },
  { href: "/#signals", label: "Signals" },
  { href: "/war-room", label: "War Room" },
  { href: "/#markets", label: "Markets" },
  { href: "/#pricing", label: "Pricing" },
  { href: "/#faq", label: "FAQ" },
];

export async function Nav() {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  const email = user?.email ?? null;

  return (
    <header className="sticky top-0 z-40 border-b border-line bg-card backdrop-blur-xl transition-all duration-300">
      <div className="page-container flex h-16 items-center justify-between">
        <Logo />
        <nav className="hidden items-center gap-8 text-sm font-medium text-slate md:flex">
          {links.map((l) => (
            <Link key={l.href} href={l.href} className="hover:text-accent">
              {l.label}
            </Link>
          ))}
        </nav>
        <div className="flex items-center gap-2">
          <ThemeToggle />
          {email ? (
            <>
              {isAdminEmail(email) ? (
                <Link href="/admin" className="btn-secondary !py-2 !px-4 !text-sm hidden sm:inline-flex">
                  Admin
                </Link>
              ) : null}
              <Link href="/dashboard" className="btn-primary-sm">
                Dashboard
              </Link>
            </>
          ) : (
            <Link href="/signup" className="btn-primary-sm">
              Get Started
            </Link>
          )}
        </div>
      </div>
    </header>
  );
}
