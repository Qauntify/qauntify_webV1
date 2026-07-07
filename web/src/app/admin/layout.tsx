import Link from "next/link";

import { signout } from "@/app/auth/actions";
import { AdminNav } from "@/components/admin/AdminNav";
import { ThemeToggle } from "@/components/shared/ThemeToggle";
import { createClient } from "@/lib/supabase/server";

// Frame only — the admin gate lives in each page (layouts are not re-rendered
// on client-side navigation, so a check here alone would not be enough).
export default async function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const supabase = await createClient();
  const { data } = await supabase.auth.getSession();
  const email = data.session?.user.email ?? "";

  return (
    <div className="flex flex-1 flex-col lg:flex-row">
      <aside className="flex shrink-0 flex-col gap-4 border-b border-line px-4 py-4 lg:min-h-dvh lg:w-56 lg:border-b-0 lg:border-r lg:px-4 lg:py-6">
        <div className="flex items-center justify-between px-3">
          <Link href="/" className="font-display text-lg tracking-tight">
            Finhub<span className="italic">KH</span>{" "}
            <span className="text-xs not-italic text-slate">admin</span>
          </Link>
          <ThemeToggle />
        </div>
        <AdminNav />
        <div className="mt-auto hidden flex-col gap-2 px-3 lg:flex">
          <p className="truncate text-xs text-slate" title={email}>
            {email}
          </p>
          <Link href="/dashboard" className="text-sm text-slate hover:text-ink">
            View site
          </Link>
          <form action={signout}>
            <button className="text-sm text-slate hover:text-ink">
              Sign out
            </button>
          </form>
        </div>
      </aside>
      <main className="flex-1 px-6 py-8 lg:px-10">{children}</main>
    </div>
  );
}
