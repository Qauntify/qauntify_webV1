/** Ops Telegram — same bot as signals, different chat (TELEGRAM_ALERTS_CHAT_ID). */

export async function sendOpsTelegram(text: string): Promise<boolean> {
  const token = process.env.TELEGRAM_BOT_TOKEN?.trim();
  const chatId = process.env.TELEGRAM_ALERTS_CHAT_ID?.trim();
  if (!token || !chatId) return false;

  try {
    const response = await fetch(
      `https://api.telegram.org/bot${token}/sendMessage`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          chat_id: chatId,
          text,
          parse_mode: "HTML",
          disable_web_page_preview: true,
        }),
        cache: "no-store",
      },
    );
    return response.ok;
  } catch {
    return false;
  }
}

export function formatCronFailAlert(opts: {
  job: string;
  detail: string;
  status?: number;
  href?: string;
  title?: string;
}): string {
  const lines = [
    `🚨 <b>${escapeHtml(opts.title ?? "Cron failed")}</b>`,
    `<b>Job</b>: ${escapeHtml(opts.job)}`,
    `<b>Why</b>: ${escapeHtml(opts.detail.slice(0, 500))}`,
  ];
  if (opts.status != null) {
    lines.push(`<b>HTTP</b>: ${opts.status}`);
  }
  if (opts.href) {
    lines.push(`<a href="${escapeHtml(opts.href)}">Open run</a>`);
  }
  return lines.join("\n");
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
