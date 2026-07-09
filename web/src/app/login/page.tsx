import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";

import { login } from "@/app/auth/actions";
import { AuthShell } from "@/components/auth/AuthShell";
import { Notice } from "@/components/shared/Notice";
import { isAdminEmail } from "@/lib/supabase/admin";
import { createClient } from "@/lib/supabase/server";

export const metadata: Metadata = {
  title: "Sign in — Qauntify",
};

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  const { error } = await searchParams;

  const supabase = await createClient();
  // getUser() re-verifies the token with the auth server, unlike
  // getSession() which just trusts the cookie's claimed contents.
  const { data: { user } } = await supabase.auth.getUser();
  if (user) {
    if (user.email && isAdminEmail(user.email)) {
      redirect("/admin");
    } else {
      redirect("/dashboard");
    }
  }

  return (
    <AuthShell
      headline="Welcome back."
      sub="Your full signal history and outcome tracking are waiting on the dashboard."
    >
      <h1 className="text-2xl font-bold">Sign in</h1>
      <p className="mt-1 text-sm text-slate">Open your trading dashboard.</p>
      {error ? (
        <Notice tone="error" className="mt-6">
          {error}
        </Notice>
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
            className="input-field"
          />
        </label>
        <label className="flex flex-col gap-1.5 text-sm font-medium">
          Password
          <input
            type="password"
            name="password"
            required
            autoComplete="current-password"
            placeholder="Your password"
            className="input-field"
          />
        </label>
        <button formAction={login} className="btn-primary mt-2">
          Sign in
        </button>
      </form>
      <p className="mt-6 text-sm text-slate">
        No account?{" "}
        <Link href="/signup" className="font-semibold text-accent hover:underline">
          Create one free
        </Link>
      </p>
    </AuthShell>
  );
}
