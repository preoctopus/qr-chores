# QR Chores — Cloud Run image
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

COPY pyproject.toml README.md uv.lock ./
COPY src ./src

# App venv (frozen lock)
RUN uv sync --frozen --no-dev

# qrc CLI + FastMCP server (separate package; installs into the same venv)
COPY clients/python/pyproject.toml clients/python/README.md ./clients/python/
COPY clients/python/src ./clients/python/src
RUN uv pip install --python /app/.venv/bin/python /app/clients/python

FROM python:3.12-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends nginx gettext-base \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 10001 appuser
WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src
COPY --from=builder /app/pyproject.toml /app/pyproject.toml
COPY --from=builder /app/README.md /app/README.md
COPY migrations ./migrations
COPY alembic.ini ./
COPY scripts/entrypoint.sh ./scripts/entrypoint.sh
COPY scripts/qrc-docker.sh ./scripts/qrc-docker.sh
COPY marketing ./marketing
COPY docker ./docker

# qrc → fixed in-container API origin (uvicorn loopback)
RUN chmod +x /app/scripts/entrypoint.sh /app/scripts/qrc-docker.sh \
    && mv /app/.venv/bin/qrc /app/.venv/bin/qrc.real \
    && cp /app/scripts/qrc-docker.sh /app/.venv/bin/qrc \
    && chmod +x /app/.venv/bin/qrc \
    && mkdir -p /var/log/nginx /var/lib/nginx /tmp \
    && chown -R appuser:appuser /app /var/log/nginx /var/lib/nginx /tmp \
    && chown -R appuser:appuser /home/appuser

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app/src" \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    RUN_MIGRATIONS=0 \
    RUN_SEED=0 \
    # FastMCP HTTP (proxied by nginx at /mcp)
    MCP_TRANSPORT=http \
    MCP_HOST=127.0.0.1 \
    MCP_PORT=8001 \
    MCP_PATH=/mcp \
    MCP_STATELESS_HTTP=1 \
    # Logging: LOG_LEVEL always; set SYSLOG_SERVER=host[:port] to dual-write to rsyslog
    LOG_LEVEL=INFO

USER appuser
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/health' % os.environ.get('PORT','8080'))" || exit 1

CMD ["/app/scripts/entrypoint.sh"]
