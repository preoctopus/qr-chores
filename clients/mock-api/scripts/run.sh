#!/usr/bin/env bash
# Start mock API. Usage: run.sh [host] [port]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOST="${1:-127.0.0.1}"
PORT="${2:-18080}"
cd "$ROOT"
if [[ ! -d .venv ]]; then
  uv sync --extra dev
fi
exec uv run uvicorn qr_chores_mock_api.app:app --host "$HOST" --port "$PORT"
