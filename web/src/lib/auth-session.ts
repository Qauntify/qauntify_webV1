import { cache } from "react";

import { createClient } from "@/lib/supabase/server";

/**
 * Cookie-only session read for Server Components.
 * `proxy.ts` refreshes the JWT when needed; pages/Nav should not call
 * `getUser()` again (that hits the Auth API on every soft navigation).
 */
export const getSessionUser = cache(async () => {
  const supabase = await createClient();
  const { data } = await supabase.auth.getSession();
  return data.session?.user ?? null;
});

export const getSessionEmail = cache(async (): Promise<string | null> => {
  const user = await getSessionUser();
  return user?.email ?? null;
});
