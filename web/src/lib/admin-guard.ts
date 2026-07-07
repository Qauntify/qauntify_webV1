import { redirect } from "next/navigation";

import { isAdminEmail } from "@/lib/supabase/admin";
import { createClient } from "@/lib/supabase/server";

// Every /admin page calls this first. getUser() verifies the session with
// the auth server — the admin gate must not trust the raw cookie contents.
export async function requireAdminPage(): Promise<string> {
  const supabase = await createClient();
  const { data } = await supabase.auth.getUser();
  const email = data.user?.email;
  if (!email) redirect("/login");
  if (!isAdminEmail(email)) redirect("/dashboard?admin=denied");
  return email;
}
