"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import {
  deleteSignal,
  deleteUser,
  getUserEmail,
  isAdminEmail,
  SIGNAL_STRATEGIES,
  updateBotSettings,
} from "@/lib/supabase/admin";
import { createClient } from "@/lib/supabase/server";

const SYMBOL_PATTERN = /^[A-Z0-9]{3,20}$/;

async function requireAdmin(): Promise<void> {
  const supabase = await createClient();
  const { data } = await supabase.auth.getUser();
  if (!isAdminEmail(data.user?.email)) redirect("/dashboard?admin=denied");
}

export async function saveBotSettings(formData: FormData) {
  await requireAdmin();

  const symbols = String(formData.get("symbols") ?? "")
    .split(",")
    .map((s) => s.trim().toUpperCase())
    .filter(Boolean);
  const confidence = Number(formData.get("minAlertConfidence"));
  const signalStrategy = String(formData.get("signalStrategy") ?? "ema_cross");

  if (symbols.length === 0 || symbols.some((s) => !SYMBOL_PATTERN.test(s))) {
    redirect(
      `/admin/ai/settings?error=${encodeURIComponent(
        "Symbols must be comma-separated Binance pairs like BTCUSDT, SOLUSDT.",
      )}`,
    );
  }
  if (!Number.isInteger(confidence) || confidence < 0 || confidence > 100) {
    redirect(
      `/admin/ai/settings?error=${encodeURIComponent(
        "Min alert confidence must be a whole number from 0 to 100.",
      )}`,
    );
  }
  if (!SIGNAL_STRATEGIES.some((s) => s.id === signalStrategy)) {
    redirect(
      `/admin/ai/settings?error=${encodeURIComponent("Pick a valid signal strategy.")}`,
    );
  }

  const ok = await updateBotSettings({
    symbols,
    minAlertConfidence: confidence,
    signalStrategy,
  });
  redirect(
    ok
      ? "/admin/ai/settings?saved=1"
      : `/admin/ai/settings?error=${encodeURIComponent(
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

export async function removeSignal(formData: FormData) {
  await requireAdmin();

  const id = String(formData.get("id") ?? "");
  if (!id) return;

  const ok = await deleteSignal(id);
  if (ok) {
    revalidatePath("/admin", "layout");
  }
}
