#!/usr/bin/env bash
# Generate a deployment-ready Slack app manifest by substituting APP_BASE_URL.
# Usage:
#   APP_BASE_URL=https://your-relay.example.com ./scripts/configure-manifest.sh
#   ./scripts/configure-manifest.sh https://your-relay.example.com
#
# Outputs slack-app-manifest-generated.yaml in the repo root.
# Upload that file at api.slack.com/apps → Your App → App Manifest → Edit.

set -euo pipefail

if [[ $# -gt 1 ]]; then
  echo "Usage: APP_BASE_URL=https://your-relay.example.com $0" >&2
  echo "   or: $0 https://your-relay.example.com" >&2
  exit 1
fi

if [[ $# -eq 1 ]]; then
  APP_BASE_URL="$1"
fi

if [[ -z "${APP_BASE_URL:-}" ]]; then
  echo "Error: APP_BASE_URL is not set." >&2
  echo "Usage: APP_BASE_URL=https://your-relay.example.com $0" >&2
  echo "   or: $0 https://your-relay.example.com" >&2
  exit 1
fi

BASE_URL="${APP_BASE_URL%/}"  # strip trailing slash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

sed "s|https://relay-beta.example.com|${BASE_URL}|g" \
  "$REPO_ROOT/slack-app-manifest.yaml" \
  > "$REPO_ROOT/slack-app-manifest-generated.yaml"

echo "Generated: $REPO_ROOT/slack-app-manifest-generated.yaml"
echo "  Events URL:       ${BASE_URL}/slack/events"
echo "  OAuth redirect:   ${BASE_URL}/slack/oauth_redirect"
echo ""
echo "Next: upload slack-app-manifest-generated.yaml at api.slack.com/apps"
