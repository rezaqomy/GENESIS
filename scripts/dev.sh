#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ -f .env ]]; then set -a; source .env; set +a; fi
backend_pid=""
frontend_pid=""
cleanup() {
  trap - EXIT INT TERM
  [[ -z "$backend_pid" ]] || kill "$backend_pid" 2>/dev/null || true
  [[ -z "$frontend_pid" ]] || kill "$frontend_pid" 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM
.venv/bin/uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000 &
backend_pid=$!
(cd frontend && exec node node_modules/vite/bin/vite.js --host 0.0.0.0) &
frontend_pid=$!
printf '\nGenesis: http://localhost:5173\nAPI docs: http://localhost:8000/docs\nCtrl+C stops both servers.\n\n'
wait -n "$backend_pid" "$frontend_pid"
