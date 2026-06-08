#!/usr/bin/env bash
# Start a full local RELAY stack (Postgres, Redis, web, worker, beat).
# Run this from the repo root after copying .env.example → .env and filling in values.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# ── env file ──────────────────────────────────────────────────────────────────
if [ ! -f .env ]; then
  echo "No .env found — copying .env.example. Fill in required values before retrying."
  cp .env.example .env
  echo "Edit .env, then re-run this script."
  exit 1
fi

# ── required env vars ─────────────────────────────────────────────────────────
for var in SLACK_CLIENT_ID SLACK_CLIENT_SECRET SLACK_SIGNING_SECRET TOKEN_ENCRYPTION_KEY ANTHROPIC_API_KEY APP_BASE_URL; do
  val=$(grep -E "^${var}=" .env | cut -d= -f2- | tr -d '"')
  if [ -z "$val" ]; then
    echo "ERROR: ${var} is not set in .env"
    exit 1
  fi
done

# ── docker-compose check ──────────────────────────────────────────────────────
if ! command -v docker compose &>/dev/null && ! command -v docker-compose &>/dev/null; then
  echo "ERROR: docker compose is not installed. See https://docs.docker.com/compose/install/"
  exit 1
fi

COMPOSE="docker compose"
command -v docker-compose &>/dev/null && COMPOSE="docker-compose"

# ── start db + redis, wait for health ────────────────────────────────────────
echo "Starting db and redis..."
$COMPOSE up -d db redis

echo "Waiting for Postgres to be ready..."
until $COMPOSE exec -T db pg_isready -U relay -q; do
  sleep 1
done

echo "Waiting for Redis to be ready..."
until $COMPOSE exec -T redis redis-cli ping | grep -q PONG; do
  sleep 1
done

# ── run migrations ────────────────────────────────────────────────────────────
echo "Running Alembic migrations..."
DATABASE_URL=$(grep -E '^DATABASE_URL=' .env | cut -d= -f2- | tr -d '"')
export DATABASE_URL
uv run alembic upgrade head

# ── start remaining services ──────────────────────────────────────────────────
echo "Starting web, worker, and beat..."
$COMPOSE up -d web worker beat

# ── health check ─────────────────────────────────────────────────────────────
echo "Waiting for web service to be ready..."
for i in $(seq 1 30); do
  if curl -sf http://localhost:3000/health >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

echo ""
echo "──────────────────────────────────────────"
echo "RELAY is running locally:"
echo "  Health:  http://localhost:3000/health"
echo "  Install: http://localhost:3000/"
echo "  Logs:    $COMPOSE logs -f web"
echo "──────────────────────────────────────────"
echo ""
echo "Next steps:"
echo "  1. Create your Slack app at https://api.slack.com/apps"
echo "     using: scripts/configure-manifest.sh http://localhost:3000"
echo "  2. Paste SLACK_CLIENT_ID, SLACK_CLIENT_SECRET, SLACK_SIGNING_SECRET into .env"
echo "  3. Restart: $COMPOSE restart web"
echo "  4. Open http://localhost:3000/ and click 'Add to Slack'"
