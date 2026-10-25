#!/usr/bin/env bash
# Start the API and Vite UI without Docker.
# Usage: ./scripts/run-local.sh
# Stop with Ctrl+C.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

API_HOST="${API_HOST:-127.0.0.1}"
API_PORT="${API_PORT:-8000}"
UI_HOST="${UI_HOST:-127.0.0.1}"
UI_PORT="${UI_PORT:-5173}"

API_PID=""
UI_PID=""

cleanup() {
  trap - EXIT INT TERM
  if [[ -n "${UI_PID}" ]] && kill -0 "${UI_PID}" 2>/dev/null; then
    kill "${UI_PID}" 2>/dev/null || true
  fi
  if [[ -n "${API_PID}" ]] && kill -0 "${API_PID}" 2>/dev/null; then
    kill "${API_PID}" 2>/dev/null || true
  fi
  wait 2>/dev/null || true
}

trap cleanup EXIT INT TERM

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

port_in_use() {
  local port="$1"
  if command -v lsof >/dev/null 2>&1; then
    lsof -nP -iTCP:"${port}" -sTCP:LISTEN >/dev/null 2>&1
  else
    return 1
  fi
}

require_cmd python3
require_cmd npm

if [[ ! -f .env ]]; then
  if [[ -f .env.example ]]; then
    cp .env.example .env
    echo "Created .env from .env.example. Edit secrets before using a live tenant."
  else
    echo "No .env or .env.example found." >&2
    exit 1
  fi
fi

if [[ ! -x .venv/bin/python ]]; then
  echo "Creating Python virtualenv..."
  python3 -m venv .venv
fi

if [[ ! -x .venv/bin/uvicorn ]]; then
  echo "Installing Python dependencies..."
  .venv/bin/pip install -r requirements-dev.txt
fi

if [[ ! -d frontend/node_modules ]]; then
  echo "Installing frontend dependencies..."
  npm --prefix frontend install
fi

mkdir -p data

if port_in_use "${API_PORT}"; then
  echo "Port ${API_PORT} is already in use. Stop that process or set API_PORT." >&2
  exit 1
fi
if port_in_use "${UI_PORT}"; then
  echo "Port ${UI_PORT} is already in use. Stop that process or set UI_PORT." >&2
  exit 1
fi

echo "Starting API on http://${API_HOST}:${API_PORT}"
PYTHONPATH=backend \
  .venv/bin/uvicorn app.main:app \
  --reload \
  --host "${API_HOST}" \
  --port "${API_PORT}" &
API_PID=$!

echo "Starting UI on http://${UI_HOST}:${UI_PORT}"
npm --prefix frontend run dev -- --host "${UI_HOST}" --port "${UI_PORT}" &
UI_PID=$!

sleep 1
if ! kill -0 "${API_PID}" 2>/dev/null; then
  echo "API failed to start." >&2
  exit 1
fi
if ! kill -0 "${UI_PID}" 2>/dev/null; then
  echo "UI failed to start." >&2
  exit 1
fi

echo
echo "Ready (no Docker)."
echo "  UI:      http://${UI_HOST}:${UI_PORT}"
echo "  API:     http://${API_HOST}:${API_PORT}"
echo "  Docs:    http://${API_HOST}:${API_PORT}/docs"
echo
echo "Press Ctrl+C to stop both processes."

wait
