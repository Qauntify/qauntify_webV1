"use server";

import { revalidatePath } from "next/cache";
import { headers } from "next/headers";
import { redirect } from "next/navigation";

import { ALLOW_SIGNUP } from "@/lib/access-mode";
import { createClient } from "@/lib/supabase/server";
import { isAdminEmail } from "@/lib/supabase/admin";

function credentials(formData: FormData): { email: string; password: string } {
  return {
    email: String(formData.get("email") ?? "").trim(),
    password: String(formData.get("password") ?? ""),
  };
}

export async function login(formData: FormData) {
  const { email, password } = credentials(formData);
  if (!email || !password) {
    redirect(`/login?error=${encodeURIComponent("បញ្ចូលអ៊ីមែល និងពាក្យសម្ងាត់របស់បងប្អូន។")}`);
  }

  const supabase = await createClient();
  const { data, error } = await supabase.auth.signInWithPassword({ email, password });
  if (error) {
    redirect(`/login?error=${encodeURIComponent(error.message)}`);
  }

  revalidatePath("/", "layout");
  if (data.user?.email && isAdminEmail(data.user.email)) {
    redirect("/admin");
  } else {
    redirect("/dashboard");
  }
}

export async function signup(formData: FormData) {
  if (!ALLOW_SIGNUP) {
    redirect(`/signup?error=${encodeURIComponent("ការចុះឈ្មោះបច្ចុប្បន្នបានបិទ។")}`);
  }

  const { email, password } = credentials(formData);
  if (!email || !password) {
    redirect(`/signup?error=${encodeURIComponent("បញ្ចូលអ៊ីមែល និងពាក្យសម្ងាត់។")}`);
  }

  const headerStore = await headers();
  const origin =
    headerStore.get("origin") ?? `http://${headerStore.get("host") ?? "localhost:3000"}`;

  const supabase = await createClient();
  const { data, error } = await supabase.auth.signUp({
    email,
    password,
    options: { emailRedirectTo: `${origin}/auth/confirm` },
  });
  if (error) {
    redirect(`/signup?error=${encodeURIComponent(error.message)}`);
  }

  // If email confirmation is disabled in Supabase, signUp returns a live
  // session — the user is already logged in.
  if (data.session) {
    revalidatePath("/", "layout");
    if (data.session.user?.email && isAdminEmail(data.session.user.email)) {
      redirect("/admin");
    } else {
      redirect("/dashboard");
    }
  }

  redirect("/signup?sent=1");
}

export async function signout() {
  const supabase = await createClient();
  await supabase.auth.signOut();
  revalidatePath("/", "layout");
  redirect("/");
}
