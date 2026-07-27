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

# ------------------------------------------------------------------------------
# Logging: SYSLOG_SERVER=host[:port] fans logs to rsyslog (UDP 514 default).
# Always also log to stdout/stderr for container platforms (Cloud Run, Docker).
# App + MCP read SYSLOG_SERVER / LOG_LEVEL from the environment.
# ------------------------------------------------------------------------------
parse_syslog_server() {
  SYSLOG_HOST=""
  SYSLOG_PORT="514"
  raw="${SYSLOG_SERVER:-}"
  if [ -z "$raw" ]; then
    return 0
  fi
  # strip optional scheme
  raw=$(echo "$raw" | sed -e 's|^udp://||' -e 's|^tcp://||' -e 's|^syslog://||')
  case "$raw" in
    *:*)
      SYSLOG_HOST="${raw%:*}"
      SYSLOG_PORT="${raw##*:}"
      ;;
    *)
      SYSLOG_HOST="$raw"
      SYSLOG_PORT="514"
      ;;
  esac
  if [ -z "$SYSLOG_HOST" ] || [ -z "$SYSLOG_PORT" ]; then
    echo "WARNING: invalid SYSLOG_SERVER='${SYSLOG_SERVER}' (expected host or host:port)" >&2
    SYSLOG_HOST=""
    SYSLOG_PORT="514"
  fi
}

parse_syslog_server
export SYSLOG_HOST SYSLOG_PORT
if [ -n "$SYSLOG_HOST" ]; then
  export SYSLOG_SERVER="${SYSLOG_HOST}:${SYSLOG_PORT}"
  echo "Syslog enabled → ${SYSLOG_SERVER} (nginx + app + MCP)"
else
  unset SYSLOG_SERVER 2>/dev/null || true
  echo "Syslog disabled (set SYSLOG_SERVER=host[:port] to enable)"
fi

# ------------------------------------------------------------------------------
# Static assets: prefer tmpfs (/dev/shm) for near-RAM serving under nginx.
# Falls back to image paths when shm is unavailable or too small.
# ------------------------------------------------------------------------------
stage_static_to_memory() {
  NGINX_MARKETING_ROOT="/app/marketing"
  NGINX_APP_STATIC_ROOT="/app/src/qr_chores/static"

  if [ ! -d /dev/shm ] || [ ! -w /dev/shm ]; then
    echo "Static roots: disk (no writable /dev/shm)"
    return 0
  fi

  # marketing ~4MB + app static ~0.4MB; require ~16MB free headroom.
  avail_kb=$(df -k /dev/shm 2>/dev/null | awk 'NR==2 {print $4}')
  if [ -n "$avail_kb" ] && [ "$avail_kb" -lt 16384 ]; then
    echo "Static roots: disk (/dev/shm low free space: ${avail_kb}k)"
    return 0
  fi

  stage="/dev/shm/qr-chores-static"
  rm -rf "$stage"
  mkdir -p "$stage"
  if cp -a /app/marketing "$stage/marketing" \
    && cp -a /app/src/qr_chores/static "$stage/app-static"; then
    NGINX_MARKETING_ROOT="$stage/marketing"
    NGINX_APP_STATIC_ROOT="$stage/app-static"
    echo "Static roots: tmpfs ${stage} (open_file_cache + RAM-backed files)"
  else
    rm -rf "$stage"
    echo "Static roots: disk (tmpfs copy failed)"
  fi
}

stage_static_to_memory
export NGINX_MARKETING_ROOT NGINX_APP_STATIC_ROOT

# ------------------------------------------------------------------------------
# Nginx log targets (primary always console; secondary optional syslog)
# ------------------------------------------------------------------------------
setup_nginx_log_vars() {
  # Always emit container-friendly console logs; optionally dual-write to syslog.
  export NGINX_ERROR_LOG_PRIMARY="/dev/stderr warn"
  export NGINX_ACCESS_LOG_PRIMARY="/dev/stdout main"
  if [ -n "$SYSLOG_HOST" ]; then
    export NGINX_ERROR_LOG_SECONDARY="error_log syslog:server=${SYSLOG_HOST}:${SYSLOG_PORT},facility=local0,tag=qr-chores-nginx,severity=warn;"
    export NGINX_ACCESS_LOG_SECONDARY="access_log syslog:server=${SYSLOG_HOST}:${SYSLOG_PORT},facility=local0,tag=qr-chores-nginx-access main;"
  else
    # Valid no-ops so envsubst always leaves a single line nginx accepts.
    export NGINX_ERROR_LOG_SECONDARY="# error_log syslog disabled"
    export NGINX_ACCESS_LOG_SECONDARY="# access_log syslog disabled"
  fi
}

setup_nginx_log_vars

if command -v nginx > /dev/null 2>&1 && [ -f /app/docker/nginx.conf.template ]; then
  echo "Generating Nginx config for PORT=${PORT} MCP=${MCP_HOST}:${MCP_PORT}${MCP_PATH}..."
  export PORT MCP_PORT
  export NGINX_MARKETING_ROOT NGINX_APP_STATIC_ROOT
  export NGINX_ERROR_LOG_PRIMARY NGINX_ERROR_LOG_SECONDARY
  export NGINX_ACCESS_LOG_PRIMARY NGINX_ACCESS_LOG_SECONDARY
  envsubst '${PORT} ${MCP_PORT} ${NGINX_MARKETING_ROOT} ${NGINX_APP_STATIC_ROOT} ${NGINX_ERROR_LOG_PRIMARY} ${NGINX_ERROR_LOG_SECONDARY} ${NGINX_ACCESS_LOG_PRIMARY} ${NGINX_ACCESS_LOG_SECONDARY}' \
    < /app/docker/nginx.conf.template > /tmp/nginx.conf

  if ! nginx -t -c /tmp/nginx.conf 2>&1; then
    echo "ERROR: nginx config test failed" >&2
    cat /tmp/nginx.conf >&2 || true
    exit 1
  fi

  # Start app + MCP in parallel (faster cold start than sequential wait loops).
  echo "Starting FastAPI app on 127.0.0.1:8000..."
  uvicorn qr_chores.main:app --host 127.0.0.1 --port 8000 &
  APP_PID=$!

  echo "Starting MCP server (${MCP_TRANSPORT}) on ${MCP_HOST}:${MCP_PORT}${MCP_PATH} → API ${APP_INTERNAL}..."
  # Unbuffered so container logs show startup failures immediately.
  python -u -m qr_chores_client &
  MCP_PID=$!

  echo "Waiting for FastAPI app to start..."
  i=0
  while [ $i -lt 50 ]; do
    if python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz')" > /dev/null 2>&1; then
      echo "FastAPI app is ready!"
      break
    fi
    if ! kill -0 "$APP_PID" 2>/dev/null; then
      echo "ERROR: FastAPI process exited before becoming ready (pid=${APP_PID})" >&2
      exit 1
    fi
    sleep 0.2
    i=$((i + 1))
  done

  # MCP readiness is best-effort and non-blocking for nginx (faster cold start).
  echo "Waiting briefly for MCP server on ${MCP_HOST}:${MCP_PORT}..."
  i=0
  while [ $i -lt 25 ]; do
    if python -c "import socket; s=socket.create_connection(('${MCP_HOST}', int('${MCP_PORT}')), 0.3); s.close()" 2>/dev/null; then
      echo "MCP server is ready!"
      break
    fi
    if ! kill -0 "$MCP_PID" 2>/dev/null; then
      echo "WARNING: MCP server process exited before becoming ready (pid=${MCP_PID})" >&2
      break
    fi
    sleep 0.2
    i=$((i + 1))
  done
  if [ $i -ge 25 ]; then
    echo "WARNING: MCP not ready yet; starting nginx anyway (MCP may come up shortly)" >&2
  fi

  echo "Starting Nginx reverse proxy on 0.0.0.0:${PORT}..."
  exec nginx -g 'daemon off;' -c /tmp/nginx.conf
else
  exec uvicorn qr_chores.main:app --host 0.0.0.0 --port "$PORT"
fi
