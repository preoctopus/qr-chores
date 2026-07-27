# QR Chores — Cloud Run image
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

COPY pyproject.toml README.md uv.lock ./
COPY src ./src

RUN uv sync --frozen --no-dev

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
COPY marketing ./marketing
COPY docker ./docker

RUN chmod +x /app/scripts/entrypoint.sh \
    && mkdir -p /var/log/nginx /var/lib/nginx /tmp \
    && chown -R appuser:appuser /app /var/log/nginx /var/lib/nginx /tmp

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    RUN_MIGRATIONS=0 \
    RUN_SEED=0

USER appuser
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/healthz' % os.environ.get('PORT','8080'))" || exit 1

CMD ["/app/scripts/entrypoint.sh"]
