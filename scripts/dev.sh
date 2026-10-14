#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ -f .env ]]; then set -a; source .env; set +a; fi
backend_pid=""
frontend_pid=""
model_pid=""
laya_pid=""
cleanup() {
  trap - EXIT INT TERM
  [[ -z "$backend_pid" ]] || kill "$backend_pid" 2>/dev/null || true
  [[ -z "$frontend_pid" ]] || kill "$frontend_pid" 2>/dev/null || true
  [[ -z "$model_pid" ]] || kill "$model_pid" 2>/dev/null || true
  [[ -z "$laya_pid" ]] || kill "$laya_pid" 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM
if [[ "${GENESIS_COGNITION:-1}" == "1" && "${GENESIS_DECISION_PROVIDER:-laya}" == "ollama" && "${GENESIS_OLLAMA_URL:-http://localhost:11435}" == "http://localhost:11435" ]]; then
  if ! curl --fail --silent --max-time 2 http://localhost:11435/api/tags >/dev/null; then
    ./scripts/local-models.sh > /tmp/genesis-ollama.log 2>&1 &
    model_pid=$!
  fi
fi
if [[ "${GENESIS_COGNITION:-1}" == "1" && "${GENESIS_DECISION_PROVIDER:-laya}" == "laya" && "${GENESIS_LAYA_URL:-http://localhost:11437}" == "http://localhost:11437" ]]; then
  if ! curl --fail --silent --max-time 2 http://localhost:11437/health >/dev/null; then
    if [[ ! -x .venv-laya/bin/uvicorn ]]; then
      printf 'Laya runtime missing: run make install-laya first.\n' >&2
      exit 1
    fi
    .venv-laya/bin/uvicorn scripts.laya_server:app --host 127.0.0.1 --port 11437 > /tmp/genesis-laya-server.log 2>&1 &
    laya_pid=$!
  fi
fi
.venv/bin/uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000 &
backend_pid=$!
(cd frontend && exec node node_modules/vite/bin/vite.js --host 0.0.0.0) &
frontend_pid=$!
printf '\nGenesis: http://localhost:5173\nAPI docs: http://localhost:8000/docs\nCtrl+C stops both servers.\n\n'
wait -n "$backend_pid" "$frontend_pid"
