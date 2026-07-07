#!/usr/bin/env bash
# Run the signals engine and the web frontend in one go.
#   ./dev.sh          — one engine scan + Next.js dev server
#   ./dev.sh --loop   — re-run the engine every hour while the frontend runs
set -euo pipefail
cd "$(dirname "$0")"

LOOP=false
[ "${1:-}" = "--loop" ] && LOOP=true

if [ ! -x .venv/bin/python ]; then
  echo "[setup] creating venv and installing engine deps..."
  python3 -m venv .venv
  .venv/bin/pip install -r requirements.txt
fi

if [ ! -d web/node_modules ]; then
  echo "[setup] installing frontend deps..."
  (cd web && npm install)
fi

run_engine() {
  if $LOOP; then
    while true; do
      .venv/bin/python -m signals.run 2>&1 | sed 's/^/[engine] /'
      echo "[engine] sleeping 1h until next scan..."
      sleep 3600
    done
  else
    .venv/bin/python -m signals.run 2>&1 | sed 's/^/[engine] /'
  fi
}

run_engine &
ENGINE_PID=$!
trap 'kill "$ENGINE_PID" 2>/dev/null || true' EXIT INT TERM

echo "[web] starting Next.js dev server..."
cd web
npm run dev
