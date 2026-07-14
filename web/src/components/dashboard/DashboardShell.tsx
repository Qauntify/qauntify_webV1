import Link from "next/link";

import { signout } from "@/app/auth/actions";
import { Logo } from "@/components/shared/Logo";
import { ThemeToggle } from "@/components/shared/ThemeToggle";
import { isAdminEmail } from "@/lib/supabase/admin";
import { createClient } from "@/lib/supabase/server";

const links = [
  { href: "/dashboard", label: "Signals", icon: "chart" },
];

export async function DashboardShell({
  children,
  title,
  subtitle,
}: {
  children: React.ReactNode;
  title: string;
  subtitle?: string;
}) {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  const email = user?.email ?? "";

  return (
    <div className="flex min-h-screen flex-1">
      <aside className="hidden w-56 flex-col border-r border-line bg-sidebar backdrop-blur-xl lg:flex fixed inset-y-0 left-0 z-40">
        <div className="flex h-16 items-center border-b border-line px-4">
          <Logo />
        </div>
        <nav className="flex flex-col gap-1 p-3">
          {links.map((l) => (
            <Link key={l.href} href={l.href} className="nav-item nav-item-active">
              <ChartIcon />
              {l.label}
            </Link>
          ))}
          {isAdminEmail(email) ? (
            <Link href="/admin" className="nav-item">
              <GearIcon />
              Admin
            </Link>
          ) : null}
        </nav>
        <div className="mt-auto border-t border-line p-4">
          <p className="truncate text-xs text-slate" title={email}>
            {email}
          </p>
          <div className="mt-3 flex items-center gap-2">
            <ThemeToggle />
            <form action={signout}>
              <button type="submit" className="btn-ghost text-xs">
                Sign out
              </button>
            </form>
          </div>
        </div>
      </aside>
      <div className="flex flex-1 flex-col lg:ml-56">
        <header className="flex h-16 items-center justify-between border-b border-line bg-card/80 backdrop-blur-xl px-4 lg:px-8 sticky top-0 z-30 transition-all duration-300">
          <div className="lg:hidden">
            <Logo />
          </div>
          <div className="hidden lg:block">
            <h1 className="text-lg font-bold">{title}</h1>
            {subtitle ? (
              <p className="text-xs text-slate">{subtitle}</p>
            ) : null}
          </div>
          <Link href="/" className="btn-ghost text-sm lg:hidden">
            Home
          </Link>
        </header>
        <main className="flex-1 p-4 lg:p-6">{children}</main>
      </div>
    </div>
  );
}

function ChartIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <path d="M3 3v18h18" />
      <path d="M7 16l4-8 4 5 5-9" />
    </svg>
  );
}

function GearIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <circle cx="12" cy="12" r="3" />
      <path d="M12 1v2m0 18v2M4.22 4.22l1.42 1.42m12.72 12.72 1.42 1.42M1 12h2m18 0h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42" />
    </svg>
  );
}
