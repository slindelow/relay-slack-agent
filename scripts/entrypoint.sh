#!/bin/bash
set -e

# Railway injects DATABASE_URL as postgresql:// — convert for asyncpg
export DATABASE_URL="${DATABASE_URL/postgresql:\/\//postgresql+asyncpg:\/\/}"
export DATABASE_URL="${DATABASE_URL/postgres:\/\//postgresql+asyncpg:\/\/}"

case "${SERVICE_TYPE:-web}" in
  web)
    echo "Running database migrations..."
    uv run alembic upgrade head
    echo "Starting web server..."
    exec uv run uvicorn relay.api.main:api --host 0.0.0.0 --port "${PORT:-3000}"
    ;;
  worker)
    exec uv run celery -A relay.worker.celery_app worker -Q default --beat --loglevel=info
    ;;
  *)
    echo "Unknown SERVICE_TYPE: ${SERVICE_TYPE}" >&2
    exit 1
    ;;
esac
