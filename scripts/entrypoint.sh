#!/usr/bin/env bash
set -euo pipefail

# Apply DB migrations (safe to run on every boot; no-op when up to date).
if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
  echo "[entrypoint] running migrations"
  python -m alembic upgrade head
fi

WORKERS="${WEB_CONCURRENCY:-3}"
echo "[entrypoint] starting gunicorn with ${WORKERS} uvicorn workers"
exec gunicorn app.main:app \
  --workers "${WORKERS}" \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind "0.0.0.0:${PORT:-8000}" \
  --timeout "${GUNICORN_TIMEOUT:-60}" \
  --graceful-timeout 30 \
  --access-logfile - --error-logfile -
