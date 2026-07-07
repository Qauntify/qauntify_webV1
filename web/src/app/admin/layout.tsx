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
      <aside className="flex w-full shrink-0 flex-col border-b border-line bg-sidebar lg:min-h-dvh lg:w-56 lg:border-b-0 lg:border-r">
        <div className="flex items-center justify-between px-4 py-4">
          <Logo suffix="admin" />
          <ThemeToggle />
        </div>
        <AdminNav />
        <div className="mt-auto hidden flex-col gap-2 border-t border-line p-4 lg:flex">
          <p className="truncate text-xs text-slate" title={email}>
            {email}
          </p>
          <Link href="/dashboard" className="btn-ghost text-sm">
            View dashboard
          </Link>
          <form action={signout}>
            <button type="submit" className="btn-ghost text-sm">
              Sign out
            </button>
          </form>
        </div>
      </aside>
      <main className="flex-1 p-6 lg:p-10">{children}</main>
    </div>
  );
}
