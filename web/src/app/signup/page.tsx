import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";

import { signup } from "@/app/auth/actions";
import { AuthShell } from "@/components/auth/AuthShell";
import { Notice } from "@/components/shared/Notice";
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
    <AuthShell
      headline="Start your journal."
      sub="AI-confirmed setups on crypto, gold, and forex — every entry logged, explained in plain language, and alerted when it matters."
    >
      <h1 className="font-display text-3xl tracking-tight">Create account</h1>
      <p className="mt-2 text-sm text-slate">
        Free forever. Unlock the full signal history.
      </p>
      {error ? (
        <Notice tone="error" className="mt-6">
          {error}
        </Notice>
      ) : null}
      {sent ? (
        <Notice tone="success" className="mt-6">
          Check your email — we sent you a confirmation link. Click it to
          finish creating your account.
        </Notice>
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
            <Link
              href="/login"
              className="font-medium text-ink underline underline-offset-4"
            >
              Sign in
            </Link>
          </p>
        </>
      )}
    </AuthShell>
  );
}
