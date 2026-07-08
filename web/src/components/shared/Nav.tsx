import Link from "next/link";

import { signout } from "@/app/auth/actions";
import { Logo } from "@/components/shared/Logo";
import { ThemeToggle } from "@/components/shared/ThemeToggle";
import { isAdminEmail } from "@/lib/supabase/admin";
import { createClient } from "@/lib/supabase/server";

const links = [
  { href: "/#features", label: "Features" },
  { href: "/#signals", label: "Signals" },
  { href: "/#markets", label: "Markets" },
  { href: "/#pricing", label: "Pricing" },
  { href: "/#faq", label: "FAQ" },
];

export async function Nav() {
  const supabase = await createClient();
  const { data } = await supabase.auth.getSession();
  const email = data.session?.user.email ?? null;

  return (
    <header className="sticky top-0 z-40 border-b border-line bg-card/90 backdrop-blur-md">
      <div className="page-container flex h-14 items-center justify-between">
        <Logo />
        <nav className="hidden items-center gap-7 text-sm font-medium text-slate md:flex">
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
                <Link href="/admin" className="btn-ghost hidden sm:inline">
                  Admin
                </Link>
              ) : null}
              <form action={signout}>
                <button type="submit" className="btn-ghost hidden sm:inline">
                  Sign out
                </button>
              </form>
            </>
          ) : (
            <Link href="/login" className="btn-ghost hidden sm:inline">
              Sign in
            </Link>
          )}
          <Link href="/dashboard" className="btn-primary-sm">
            Dashboard
          </Link>
        </div>
      </div>
    </header>
  );
}
