#!/usr/bin/env bash
# Post a cron/workflow failure to TELEGRAM_ALERTS_CHAT_ID (same bot, ops channel).
# No-op when token or alerts chat id is empty.
set -euo pipefail

if [[ -z "${TELEGRAM_BOT_TOKEN:-}" || -z "${TELEGRAM_ALERTS_CHAT_ID:-}" ]]; then
  echo "TELEGRAM_ALERTS_CHAT_ID not set — skip Telegram failure alert"
  exit 0
fi

JOB_NAME="${CRON_JOB_NAME:-${GITHUB_WORKFLOW:-cron}}"
RUN_URL="${GITHUB_SERVER_URL:-}/${GITHUB_REPOSITORY:-}/actions/runs/${GITHUB_RUN_ID:-}"
EVENT="${GITHUB_EVENT_NAME:-unknown}"
REF="${GITHUB_REF_NAME:-unknown}"
DETAIL="${CRON_FAIL_DETAIL:-Workflow job failed}"

# Telegram HTML
TEXT=$(printf '🚨 <b>Cron failed</b>\n<b>Job</b>: %s\n<b>Event</b>: %s\n<b>Branch</b>: %s\n<b>Why</b>: %s\n<a href="%s">Open run #%s</a>' \
  "$JOB_NAME" "$EVENT" "$REF" "$DETAIL" "$RUN_URL" "${GITHUB_RUN_NUMBER:-?}")

curl -sS -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
  --data-urlencode "chat_id=${TELEGRAM_ALERTS_CHAT_ID}" \
  --data-urlencode "parse_mode=HTML" \
  --data-urlencode "disable_web_page_preview=true" \
  --data-urlencode "text=${TEXT}" \
  >/dev/null || echo "Telegram notify failed (non-fatal)"
