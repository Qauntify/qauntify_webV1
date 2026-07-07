"use server";

import { redirect } from "next/navigation";

import {
  deleteUser,
  getUserEmail,
  isAdminEmail,
  updateBotSettings,
} from "@/lib/supabase/admin";
import { createClient } from "@/lib/supabase/server";

const SYMBOL_PATTERN = /^[A-Z0-9]{3,20}$/;

async function requireAdmin(): Promise<void> {
  const supabase = await createClient();
  const { data } = await supabase.auth.getUser();
  if (!isAdminEmail(data.user?.email)) redirect("/dashboard");
}

export async function saveBotSettings(formData: FormData) {
  await requireAdmin();

  const symbols = String(formData.get("symbols") ?? "")
    .split(",")
    .map((s) => s.trim().toUpperCase())
    .filter(Boolean);
  const confidence = Number(formData.get("minAlertConfidence"));

  if (symbols.length === 0 || symbols.some((s) => !SYMBOL_PATTERN.test(s))) {
    redirect(
      `/admin/bot?error=${encodeURIComponent(
        "Symbols must be comma-separated Binance pairs like BTCUSDT, SOLUSDT.",
      )}`,
    );
  }
  if (!Number.isInteger(confidence) || confidence < 0 || confidence > 100) {
    redirect(
      `/admin/bot?error=${encodeURIComponent(
        "Min alert confidence must be a whole number from 0 to 100.",
      )}`,
    );
  }

  const ok = await updateBotSettings({
    symbols,
    minAlertConfidence: confidence,
  });
  redirect(
    ok
      ? "/admin/bot?saved=1"
      : `/admin/bot?error=${encodeURIComponent(
          "Could not save settings — is the bot_settings table created (run supabase/schema.sql)?",
        )}`,
  );
}

export async function removeUser(formData: FormData) {
  await requireAdmin();

  const id = String(formData.get("id") ?? "");
  if (!id) redirect("/admin/users");

  // Never delete an admin account (including your own).
  const email = await getUserEmail(id);
  if (isAdminEmail(email)) {
    redirect(
      `/admin/users?error=${encodeURIComponent("Admin accounts cannot be deleted.")}`,
    );
  }

  const ok = await deleteUser(id);
  redirect(
    ok
      ? "/admin/users?deleted=1"
      : `/admin/users?error=${encodeURIComponent("Could not delete that user.")}`,
  );
}
