#!/bin/bash
set -e

# Railway injects DATABASE_URL as postgresql://; SQLAlchemy asyncpg requires
# postgresql+asyncpg://. Keep this aligned with scripts/start_web.sh.
export DATABASE_URL="${DATABASE_URL/postgresql:\/\//postgresql+asyncpg:\/\/}"
export DATABASE_URL="${DATABASE_URL/postgres:\/\//postgresql+asyncpg:\/\/}"

case "${1:-worker}" in
  worker)
    exec uv run celery -A relay.worker.celery_app.celery worker --loglevel=INFO
    ;;
  beat)
    exec uv run celery -A relay.worker.celery_app.celery beat --loglevel=INFO
    ;;
  *)
    echo "Usage: $0 [worker|beat]" >&2
    exit 1
    ;;
esac
