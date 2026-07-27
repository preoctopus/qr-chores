#!/bin/sh
# In-container qrc: always talk to uvicorn on loopback (not nginx / public BASE_URL).
exec /app/.venv/bin/qrc.real --base-url http://127.0.0.1:8000 "$@"
