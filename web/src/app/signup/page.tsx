import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";

import { signup } from "@/app/auth/actions";
import { AuthShell } from "@/components/auth/AuthShell";
import { Notice } from "@/components/shared/Notice";
import { createClient } from "@/lib/supabase/server";

export const metadata: Metadata = {
  title: "Create account — Qauntify",
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
      headline="Start tracking signals."
      sub="AI-confirmed setups with entry, stop loss, take profit, and outcome tracking."
    >
      <h1 className="text-2xl font-bold">Create account</h1>
      <p className="mt-1 text-sm text-slate">Free forever. Full signal history.</p>
      {error ? (
        <Notice tone="error" className="mt-6">
          {error}
        </Notice>
      ) : null}
      {sent ? (
        <Notice tone="success" className="mt-6">
          Check your email — we sent a confirmation link.
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
                className="input-field"
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
                className="input-field"
              />
            </label>
            <button formAction={signup} className="btn-primary mt-2">
              Create account
            </button>
          </form>
          <p className="mt-6 text-sm text-slate">
            Already have an account?{" "}
            <Link href="/login" className="font-semibold text-accent hover:underline">
              Sign in
            </Link>
          </p>
        </>
      )}
    </AuthShell>
  );
}
