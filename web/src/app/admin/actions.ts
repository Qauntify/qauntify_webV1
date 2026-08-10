"use server";

import { randomUUID } from "crypto";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import {
  deleteSignal,
  deleteToolRow,
  deleteToolStorageObject,
  deleteUser,
  getToolById,
  getUserEmail,
  insertTool,
  isAdminEmail,
  SIGNAL_STRATEGIES,
  updateBotSettings,
  updateToolPublished,
  uploadToolFile,
} from "@/lib/supabase/admin";
import { canonicalMarketSymbol } from "@/lib/markets/kraken";
import { parseToolCategory, TOOL_CATEGORIES } from "@/lib/tools";
import { createClient } from "@/lib/supabase/server";

const SYMBOL_PATTERN = /^[A-Z0-9]{3,20}$/;
const TOOL_MAX_BYTES = 25 * 1024 * 1024;
const URL_PATTERN = /^https?:\/\/.+/i;

async function requireAdmin(): Promise<void> {
  const supabase = await createClient();
  const { data } = await supabase.auth.getUser();
  if (!isAdminEmail(data.user?.email)) redirect("/dashboard?admin=denied");
}

export async function saveBotSettings(formData: FormData) {
  await requireAdmin();

  const symbols = String(formData.get("symbols") ?? "")
    .split(",")
    .map((s) => canonicalMarketSymbol(s.trim()))
    .filter((s) => Boolean(s) && s !== "GBPUSD");
  const alertConfidence = Number(formData.get("minAlertConfidence"));
  const storeConfidence = Number(formData.get("minStoreConfidence"));
  const signalStrategy = String(formData.get("signalStrategy") ?? "ema_cross");

  if (symbols.length === 0 || symbols.some((s) => !SYMBOL_PATTERN.test(s))) {
    redirect(
      `/admin/ai/settings?error=${encodeURIComponent(
        "Symbols must be comma-separated USD pairs like BTCUSD, ETHUSD.",
      )}`,
    );
  }
  if (!Number.isInteger(alertConfidence) || alertConfidence < 0 || alertConfidence > 100) {
    redirect(
      `/admin/ai/settings?error=${encodeURIComponent(
        "Min alert confidence must be a whole number from 0 to 100.",
      )}`,
    );
  }
  if (!Number.isInteger(storeConfidence) || storeConfidence < 0 || storeConfidence > 100) {
    redirect(
      `/admin/ai/settings?error=${encodeURIComponent(
        "Min store confidence must be a whole number from 0 to 100.",
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
    minAlertConfidence: alertConfidence,
    minStoreConfidence: storeConfidence,
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
    revalidatePath("/admin/calendar");
    revalidatePath("/admin/signals");
    revalidatePath("/dashboard");

  }
}

function revalidateTools() {
  revalidatePath("/tools");
  revalidatePath("/admin/tools");
}

export async function createTool(formData: FormData) {
  await requireAdmin();

  const titleKm = String(formData.get("title_km") ?? "").trim();
  const descriptionKm = String(formData.get("description_km") ?? "").trim();
  const category = parseToolCategory(String(formData.get("category") ?? "other"));
  const sortOrder = Number(formData.get("sort_order") ?? 0);
  const externalUrl = String(formData.get("external_url") ?? "").trim();
  const file = formData.get("file");

  if (titleKm.length < 2) {
    redirect(
      `/admin/tools?error=${encodeURIComponent("Title (Khmer) must be at least 2 characters.")}`,
    );
  }
  if (!Number.isFinite(sortOrder)) {
    redirect(`/admin/tools?error=${encodeURIComponent("Sort order must be a number.")}`);
  }

  const hasFile = file instanceof File && file.size > 0;
  const hasLink = externalUrl.length > 0;

  if (!hasFile && !hasLink) {
    redirect(
      `/admin/tools?error=${encodeURIComponent("Upload a file or provide an external URL.")}`,
    );
  }
  if (hasFile && hasLink) {
    redirect(
      `/admin/tools?error=${encodeURIComponent("Use either a file upload or an external URL, not both.")}`,
    );
  }
  if (hasLink && !URL_PATTERN.test(externalUrl)) {
    redirect(
      `/admin/tools?error=${encodeURIComponent("External URL must start with http:// or https://")}`,
    );
  }
  if (hasFile && file.size > TOOL_MAX_BYTES) {
    redirect(
      `/admin/tools?error=${encodeURIComponent("File is too large (max 25 MB).")}`,
    );
  }

  const id = randomUUID();
  let fileUrl: string | null = null;
  let fileName: string | null = null;
  let mimeType: string | null = null;
  let fileSize: number | null = null;
  let link: string | null = null;

  if (hasFile) {
    const bytes = Buffer.from(await file.arrayBuffer());
    fileName = file.name.trim() || "download";
    mimeType = file.type || "application/octet-stream";
    fileSize = bytes.length;
    fileUrl = await uploadToolFile(id, fileName, bytes, mimeType);
    if (!fileUrl) {
      redirect(
        `/admin/tools?error=${encodeURIComponent("File upload failed — check Supabase Storage tools bucket.")}`,
      );
    }
  } else {
    link = externalUrl;
  }

  const ok = await insertTool({
    id,
    title_km: titleKm,
    description_km: descriptionKm,
    category,
    file_url: fileUrl,
    file_name: fileName,
    mime_type: mimeType,
    file_size: fileSize,
    external_url: link,
    sort_order: Math.round(sortOrder),
    published: true,
  });

  if (!ok) {
    if (fileUrl) await deleteToolStorageObject(fileUrl);
    redirect(
      `/admin/tools?error=${encodeURIComponent("Could not save tool — run the tools migration in Supabase.")}`,
    );
  }

  revalidateTools();
  redirect("/admin/tools?saved=1");
}

export async function toggleToolPublished(formData: FormData) {
  await requireAdmin();

  const id = String(formData.get("id") ?? "");
  const published = String(formData.get("published") ?? "") === "true";
  if (!id) redirect("/admin/tools");

  const ok = await updateToolPublished(id, published);
  revalidateTools();
  redirect(
    ok
      ? "/admin/tools?saved=1"
      : `/admin/tools?error=${encodeURIComponent("Could not update tool visibility.")}`,
  );
}

export async function removeTool(formData: FormData) {
  await requireAdmin();

  const id = String(formData.get("id") ?? "");
  if (!id) redirect("/admin/tools");

  const row = await getToolById(id);
  if (row?.file_url) await deleteToolStorageObject(row.file_url);

  const ok = await deleteToolRow(id);
  revalidateTools();
  redirect(
    ok
      ? "/admin/tools?deleted=1"
      : `/admin/tools?error=${encodeURIComponent("Could not delete tool.")}`,
  );
}
