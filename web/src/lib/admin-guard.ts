import { cache } from "react";
import { redirect } from "next/navigation";

import { getSessionEmail as sessionEmail } from "@/lib/auth-session";
import { isAdminEmail } from "@/lib/admin-emails";

/**
 * Auth helpers for admin pages.
 *
 * `proxy.ts` refreshes the JWT when needed. These helpers read the session
 * from cookies so Server Components do not pay a second Auth API round-trip.
 */
export const getSessionEmail = sessionEmail;

// Every /admin page calls this first. Relies on proxy having refreshed the
// session; we only check the cookie + ADMIN_EMAILS allow-list here.
export const requireAdminPage = cache(async (): Promise<string> => {
  const email = await getSessionEmail();
  if (!email) redirect("/login");
  if (!isAdminEmail(email)) redirect("/dashboard?admin=denied");
  return email;
});
