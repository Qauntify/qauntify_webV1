import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";

import { signup } from "@/app/auth/actions";
import { AuthShell } from "@/components/auth/AuthShell";
import { Notice } from "@/components/shared/Notice";
import { ALLOW_SIGNUP } from "@/lib/access-mode";
import { createClient } from "@/lib/supabase/server";

export const metadata: Metadata = {
  title: "បង្កើតគណនី — Qauntify",
};

export default async function SignupPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; sent?: string }>;
}) {
  const { error, sent } = await searchParams;

  const supabase = await createClient();
  // getUser() re-verifies the token with the auth server, unlike
  // getSession() which just trusts the cookie's claimed contents.
  const { data: { user } } = await supabase.auth.getUser();
  if (user) redirect("/dashboard");

  return (
    <AuthShell
      headline="ចាប់ផ្តើមតាមដាន signals។"
      sub="ការរៀបចំដែល AI បញ្ជាក់ ជាមួយចូល បញ្ឈប់ខាត យកចំណេញ និងការតាមដានលទ្ធផល។"
    >
      <h1 className="text-2xl font-bold">បង្កើតគណនី</h1>
      <p className="mt-1 text-sm text-slate">ឥតគិតថ្លៃជារៀងរហូត។ ប្រវត្តិ signals ពេញលេញ។</p>
      {!ALLOW_SIGNUP ? (
        <Notice tone="success" className="mt-6">
          ការចុះឈ្មោះបច្ចុប្បន្នបានបិទ — signals អាចមើលឥតគិតថ្លៃ
          ដោយមិនចាំបាច់មានគណនី។ ទៅកាន់{" "}
          <Link href="/signals" className="font-semibold underline">
            Signals
          </Link>{" "}
          ដើម្បីមើលអ្វីដែលម៉ាស៊ីនកំពុងរកឃើញ។
        </Notice>
      ) : (
        <>
          {error ? (
            <Notice tone="error" className="mt-6">
              {error}
            </Notice>
          ) : null}
          {sent ? (
            <Notice tone="success" className="mt-6">
              ពិនិត្យអ៊ីមែលរបស់បងប្អូន — យើងបានផ្ញើតំណភ្ជាប់បញ្ជាក់។
            </Notice>
          ) : (
            <form className="mt-8 flex flex-col gap-4">
              <label className="flex flex-col gap-1.5 text-sm font-medium">
                អ៊ីមែល
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
                ពាក្យសម្ងាត់
                <input
                  type="password"
                  name="password"
                  required
                  minLength={6}
                  autoComplete="new-password"
                  placeholder="យ៉ាងហោចណាស់ ៦ តួអក្សរ"
                  className="input-field"
                />
              </label>
              <button formAction={signup} className="btn-primary mt-2">
                បង្កើតគណនី
              </button>
            </form>
          )}
        </>
      )}
      <p className="mt-6 text-sm text-slate">
        មានគណនីរួចហើយ?{" "}
        <Link href="/login" className="font-semibold text-accent hover:underline">
          ចូលគណនី
        </Link>
      </p>
    </AuthShell>
  );
}
