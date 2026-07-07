import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";

import { signup } from "@/app/auth/actions";
import { Footer } from "@/components/shared/Footer";
import { Nav } from "@/components/shared/Nav";
import { createClient } from "@/lib/supabase/server";

export const metadata: Metadata = {
  title: "Create account — FinhubKH",
};

export default async function SignupPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; sent?: string }>;
}) {
  const { error, sent } = await searchParams;

  const supabase = await createClient();
  const { data } = await supabase.auth.getSession();
  if (data.session) redirect("/dashboard");

  return (
    <>
      <Nav />
      <main className="flex-1">
        <div className="mx-auto max-w-sm px-6 py-20">
          <h1 className="font-display text-4xl tracking-tight">Create account</h1>
          <p className="mt-2 text-sm text-slate">
            Free forever. Unlock the full signal history past 24 hours.
          </p>
          {error ? (
            <p className="mt-6 rounded-lg bg-short-soft px-4 py-3 text-sm text-short">
              {error}
            </p>
          ) : null}
          {sent ? (
            <div className="mt-6 rounded-lg bg-long-soft px-4 py-3 text-sm text-long">
              Check your email — we sent you a confirmation link. Click it to
              finish creating your account.
            </div>
          ) : (
            <>
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
                    minLength={6}
                    autoComplete="new-password"
                    placeholder="At least 6 characters"
                    className="rounded-lg border border-line bg-card px-3 py-2 text-sm font-normal outline-none focus:border-slate"
                  />
                </label>
                <button
                  formAction={signup}
                  className="mt-2 rounded-lg bg-ink px-4 py-2.5 text-sm font-medium text-paper hover:bg-ink/85"
                >
                  Create account
                </button>
              </form>
              <p className="mt-6 text-sm text-slate">
                Already have an account?{" "}
                <Link href="/login" className="font-medium text-ink underline underline-offset-4">
                  Sign in
                </Link>
              </p>
            </>
          )}
        </div>
      </main>
      <Footer />
    </>
  );
}
