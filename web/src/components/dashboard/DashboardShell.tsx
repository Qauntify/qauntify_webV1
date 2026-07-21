import Link from "next/link";

import { signout } from "@/app/auth/actions";
import { DashboardNav } from "@/components/dashboard/DashboardNav";
import { Logo } from "@/components/shared/Logo";
import { ThemeToggle } from "@/components/shared/ThemeToggle";
import { isAdminEmail } from "@/lib/supabase/admin";
import { createClient } from "@/lib/supabase/server";

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
  const {
    data: { user },
  } = await supabase.auth.getUser();
  const email = user?.email ?? "";

  return (
    <div className="flex min-h-screen flex-1">
      <aside className="hidden w-56 flex-col border-r border-line bg-sidebar backdrop-blur-xl lg:flex fixed inset-y-0 left-0 z-40">
        <div className="flex h-16 items-center border-b border-line px-4">
          <Logo />
        </div>
        <DashboardNav showAdmin={isAdminEmail(email)} />
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
      <div className="flex min-w-0 flex-1 flex-col lg:ml-56">
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
          <div className="flex items-center gap-2 lg:hidden">
            <Link href="/dashboard/markets" className="btn-ghost text-sm">
              Markets
            </Link>
            <Link href="/" className="btn-ghost text-sm">
              Home
            </Link>
          </div>
        </header>
        <main className="min-w-0 flex-1 overflow-x-hidden p-4 lg:p-6">
          {children}
        </main>
      </div>
    </div>
  );
}
