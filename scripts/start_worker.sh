#!/bin/bash
set -e

# Railway injects DATABASE_URL as postgresql:// — convert for asyncpg
export DATABASE_URL="${DATABASE_URL/postgresql:\/\//postgresql+asyncpg:\/\/}"
export DATABASE_URL="${DATABASE_URL/postgres:\/\//postgresql+asyncpg:\/\/}"

exec uv run celery -A relay.worker.celery_app worker -Q default --beat --loglevel=info
