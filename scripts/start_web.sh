#!/bin/bash
set -e

# Railway (and most PaaS providers) inject DATABASE_URL as postgresql://
# SQLAlchemy asyncpg requires postgresql+asyncpg://
export DATABASE_URL="${DATABASE_URL/postgresql:\/\//postgresql+asyncpg:\/\/}"
export DATABASE_URL="${DATABASE_URL/postgres:\/\//postgresql+asyncpg:\/\/}"

echo "Running database migrations..."
uv run alembic upgrade head

echo "Starting web server..."
exec uv run uvicorn relay.api.main:api --host 0.0.0.0 --port "${PORT:-3000}"
