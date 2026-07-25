#!/bin/sh
# Cloud Run / Docker entrypoint
set -e

if [ "${RUN_MIGRATIONS:-0}" = "1" ]; then
  echo "Running Alembic migrations..."
  alembic upgrade head
fi

if [ "${RUN_SEED:-0}" = "1" ]; then
  echo "Seeding users and default achievements..."
  qr-chores-seed
fi

PORT="${PORT:-8080}"
exec uvicorn qr_chores.main:app --host 0.0.0.0 --port "$PORT"
