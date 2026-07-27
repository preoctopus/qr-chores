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

# In-container FastAPI bind (nginx proxies here; qrc + MCP always use this).
APP_INTERNAL=http://127.0.0.1:8000

export MCP_TRANSPORT="${MCP_TRANSPORT:-http}"
export MCP_HOST="${MCP_HOST:-127.0.0.1}"
export MCP_PORT="${MCP_PORT:-8001}"
export MCP_PATH="${MCP_PATH:-/mcp}"
export MCP_STATELESS_HTTP="${MCP_STATELESS_HTTP:-1}"

if command -v nginx > /dev/null 2>&1 && [ -f /app/docker/nginx.conf.template ]; then
  echo "Generating Nginx config for PORT=${PORT} MCP=${MCP_HOST}:${MCP_PORT}${MCP_PATH}..."
  export MCP_PORT
  envsubst '${PORT} ${MCP_PORT}' < /app/docker/nginx.conf.template > /tmp/nginx.conf

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

  echo "Starting MCP server (${MCP_TRANSPORT}) on ${MCP_HOST}:${MCP_PORT}${MCP_PATH} → API ${APP_INTERNAL}..."
  # Tools default to http://127.0.0.1:8000 when MCP_TRANSPORT is HTTP (see mcp_server).
  python -m qr_chores_client &

  echo "Starting Nginx reverse proxy on 0.0.0.0:${PORT}..."
  exec nginx -g 'daemon off;' -c /tmp/nginx.conf
else
  exec uvicorn qr_chores.main:app --host 0.0.0.0 --port "$PORT"
fi
