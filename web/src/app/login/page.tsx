import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";

import { login } from "@/app/auth/actions";
import { Footer } from "@/components/shared/Footer";
import { Nav } from "@/components/shared/Nav";
import { createClient } from "@/lib/supabase/server";

export const metadata: Metadata = {
  title: "Sign in — FinhubKH",
};

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  const { error } = await searchParams;

  const supabase = await createClient();
  const { data } = await supabase.auth.getSession();
  if (data.session) redirect("/dashboard");

  return (
    <>
      <Nav />
      <main className="flex-1">
        <div className="mx-auto max-w-sm px-6 py-20">
          <h1 className="font-display text-4xl tracking-tight">Sign in</h1>
          <p className="mt-2 text-sm text-slate">
            Welcome back. Sign in to see the full signal history.
          </p>
          {error ? (
            <p className="mt-6 rounded-lg bg-short-soft px-4 py-3 text-sm text-short">
              {error}
            </p>
          ) : null}
          <form className="mt-8 flex flex-col gap-4">
            <label className="flex flex-col gap-1.5 text-sm font-medium">
              Email
              <input
                type="email"
                name="email"
                required
                autoComplete="email"
                placeholder="you@example.com"
                className="rounded-lg border border-line bg-card px-3 py-2 text-sm font-normal outline-none focus:border-slate"
              />
            </label>
            <label className="flex flex-col gap-1.5 text-sm font-medium">
              Password
              <input
                type="password"
                name="password"
                required
                autoComplete="current-password"
                placeholder="••••••••"
                className="rounded-lg border border-line bg-card px-3 py-2 text-sm font-normal outline-none focus:border-slate"
              />
            </label>
            <button
              formAction={login}
              className="mt-2 rounded-lg bg-ink px-4 py-2.5 text-sm font-medium text-paper hover:bg-ink/85"
            >
              Sign in
            </button>
          </form>
          <p className="mt-6 text-sm text-slate">
            No account yet?{" "}
            <Link href="/signup" className="font-medium text-ink underline underline-offset-4">
              Create one free
            </Link>
          </p>
        </div>
      </main>
      <Footer />
    </>
  );
}
