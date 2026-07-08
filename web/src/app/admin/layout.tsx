import Link from "next/link";

import { signout } from "@/app/auth/actions";
import { AdminNav } from "@/components/admin/AdminNav";
import { Logo } from "@/components/shared/Logo";
import { ThemeToggle } from "@/components/shared/ThemeToggle";
import { createClient } from "@/lib/supabase/server";

export default async function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const supabase = await createClient();
  const { data } = await supabase.auth.getSession();
  const email = data.session?.user.email ?? "";

  return (
    <div className="flex min-h-full flex-1">
      <aside className="hidden w-56 shrink-0 flex-col border-r border-line bg-sidebar lg:flex">
        <div className="flex h-14 items-center border-b border-line px-4">
          <Logo suffix="admin" />
        </div>
        <div className="pt-3">
          <AdminNav />
        </div>
        <div className="mt-auto border-t border-line p-4">
          <p className="truncate text-xs text-slate" title={email}>
            {email}
          </p>
          <div className="mt-3 flex flex-col gap-2">
            <Link href="/dashboard" className="btn-ghost text-xs text-slate justify-start px-2 py-1.5 -ml-2">
              &larr; View dashboard
            </Link>
            <div className="flex items-center gap-2">
              <ThemeToggle />
              <form action={signout}>
                <button type="submit" className="btn-ghost text-xs">
                  Sign out
                </button>
              </form>
            </div>
          </div>
        </div>
      </aside>
      <div className="flex flex-1 flex-col">
        <header className="flex h-14 items-center justify-between border-b border-line bg-card px-4 lg:px-8">
          <div className="lg:hidden">
            <Logo suffix="admin" />
          </div>
          <div className="hidden lg:block">
            {/* Desktop header left area */}
          </div>
          <div className="flex items-center gap-3 lg:hidden">
            <Link href="/dashboard" className="text-xs text-slate hover:text-ink">
              Dashboard
            </Link>
            <ThemeToggle />
            <form action={signout}>
              <button type="submit" className="btn-ghost text-xs">
                Sign out
              </button>
            </form>
          </div>
        </header>
        <div className="block border-b border-line bg-sidebar pt-3 lg:hidden">
          <AdminNav />
        </div>
        <main className="flex-1 p-4 lg:p-6">{children}</main>
      </div>
    </div>
  );
}
