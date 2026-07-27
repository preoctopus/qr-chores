#!/bin/sh
# Cloud Run / Docker entrypoint
set -e
export PYTHONPATH="/app/src:${PYTHONPATH}"

if [ "${RUN_MIGRATIONS:-0}" = "1" ]; then
  echo "Running Alembic migrations..."
  alembic upgrade head
fi

if [ "${RUN_SEED:-0}" = "1" ]; then
  echo "Seeding users and default achievements..."
  qr-chores-seed
fi

PORT="${PORT:-8080}"

if command -v nginx > /dev/null 2>&1 && [ -f /app/docker/nginx.conf.template ]; then
  echo "Generating Nginx config for PORT=${PORT}..."
  envsubst '${PORT}' < /app/docker/nginx.conf.template > /tmp/nginx.conf

  echo "Starting FastAPI app on 127.0.0.1:8000..."
  uvicorn qr_chores.main:app --host 127.0.0.1 --port 8000 &

  echo "Waiting for FastAPI app to start..."
  i=0
  while [ $i -lt 50 ]; do
    if python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz')" > /dev/null 2>&1; then
      echo "FastAPI app is ready!"
      break
    fi
    sleep 0.2
    i=$((i+1))
  done

  echo "Starting Nginx reverse proxy on 0.0.0.0:${PORT}..."
  exec nginx -g 'daemon off;' -c /tmp/nginx.conf
else
  exec uvicorn qr_chores.main:app --host 0.0.0.0 --port "$PORT"
fi
