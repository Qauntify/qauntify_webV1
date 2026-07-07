import Link from "next/link";

import { signout } from "@/app/auth/actions";
import { ThemeToggle } from "@/components/shared/ThemeToggle";
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
    <header className="sticky top-0 z-40 border-b border-line bg-paper/90 backdrop-blur-sm">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-6">
        <Link href="/" className="font-display text-xl tracking-tight">
          Finhub<span className="italic">KH</span>
        </Link>
        <nav className="hidden items-center gap-7 text-sm text-slate md:flex">
          {links.map((l) => (
            <Link key={l.href} href={l.href} className="hover:text-ink">
              {l.label}
            </Link>
          ))}
        </nav>
        <div className="flex items-center gap-3">
          <ThemeToggle />
          {email ? (
            <>
              <span className="hidden max-w-40 truncate text-sm text-slate sm:block">
                {email}
              </span>
              <form action={signout}>
                <button className="text-sm text-slate hover:text-ink">
                  Sign out
                </button>
              </form>
            </>
          ) : (
            <Link href="/login" className="text-sm text-slate hover:text-ink">
              Sign in
            </Link>
          )}
          <Link
            href="/dashboard"
            className="rounded-lg bg-ink px-4 py-2 text-sm font-medium text-paper hover:bg-ink/85"
          >
            Dashboard
          </Link>
        </div>
      </div>
    </header>
  );
}
