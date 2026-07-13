import { cache } from "react";
import { redirect } from "next/navigation";

import { isAdminEmail } from "@/lib/supabase/admin";
import { createClient } from "@/lib/supabase/server";

/**
 * Auth helpers for admin pages.
 *
 * `proxy.ts` already calls getUser() once per request (session refresh).
 * These helpers read the refreshed session from cookies so Server Components
 * do not pay a second Auth API round-trip on every navigation.
 */
export const getSessionEmail = cache(async (): Promise<string | null> => {
  const supabase = await createClient();
  const { data } = await supabase.auth.getSession();
  return data.session?.user?.email ?? null;
});

// Every /admin page calls this first. Relies on proxy having refreshed the
// session; we only check the cookie + ADMIN_EMAILS allow-list here.
export const requireAdminPage = cache(async (): Promise<string> => {
  const email = await getSessionEmail();
  if (!email) redirect("/login");
  if (!isAdminEmail(email)) redirect("/dashboard?admin=denied");
  return email;
});
