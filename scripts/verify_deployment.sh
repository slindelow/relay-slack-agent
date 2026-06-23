#!/usr/bin/env bash
# Automated pre-validation for the beta validation checklist.
# Checks everything that can be verified without Slack workspace interaction.
# Usage: ./scripts/verify_deployment.sh [APP_BASE_URL]
# Default APP_BASE_URL: https://web-production-acd3.up.railway.app

set -euo pipefail

APP_BASE_URL="${1:-https://web-production-acd3.up.railway.app}"
BASE="${APP_BASE_URL%/}"
PASS=0
FAIL=0

check() {
  local name="$1"
  local result="$2"
  local expected="$3"
  if echo "$result" | grep -q "$expected"; then
    echo "✅ $name"
    PASS=$((PASS + 1))
  else
    echo "❌ $name"
    echo "   Expected: $expected"
    echo "   Got:      $result"
    FAIL=$((FAIL + 1))
  fi
}

echo "=== RELAY Deployment Pre-Validation ==="
echo "Target: $BASE"
echo ""

# --- Infrastructure checks ---
echo "--- Infrastructure ---"
HEALTH=$(curl -s --max-time 10 "$BASE/health")
check "Health endpoint reachable" "$HEALTH" '"status":"ok"'
check "Database healthy" "$HEALTH" '"db":"ok"'
check "Redis healthy" "$HEALTH" '"redis":"ok"'

INSTALL_STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "$BASE/")
check "Install page returns 200" "$INSTALL_STATUS" "200"

SLACK_INSTALL=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "$BASE/slack/install")
check "Slack install endpoint returns 200" "$SLACK_INSTALL" "200"

# --- MCP server ---
echo ""
echo "--- MCP Server ---"
MCP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "$BASE/mcp/sse" 2>/dev/null || echo "000")
if [ "$MCP_STATUS" = "200" ] || [ "$MCP_STATUS" = "307" ] || [ "$MCP_STATUS" = "200" ]; then
  echo "✅ MCP /mcp/sse endpoint reachable (HTTP $MCP_STATUS)"
  PASS=$((PASS + 1))
else
  echo "⚠️  MCP /mcp/sse returned HTTP $MCP_STATUS (may need a client to connect)"
fi

# --- Legal/public pages ---
echo ""
echo "--- Public Pages ---"
PRIVACY=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "$BASE/privacy")
check "Privacy page" "$PRIVACY" "200"
TERMS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "$BASE/terms")
check "Terms page" "$TERMS" "200"

# --- Summary ---
echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
echo ""
if [ $FAIL -eq 0 ]; then
  echo "✅ All automated checks pass. Proceed to manual Slack steps 3-14."
else
  echo "❌ $FAIL check(s) failed. Fix before proceeding."
fi
echo ""
echo "--- Next: Manual Steps in Slack ---"
echo "Step 3:  In RELAY Beta workspace: /relay register #test-channel TestCo"
echo "Step 4:  /relay settings → Connect HubSpot (requires HUBSPOT env vars in Railway)"
echo "Step 5:  /relay settings → Connect GitHub (requires VOYAGE_API_KEY in Railway)"
echo "Steps 6-14: Follow docs/deployment/beta-validation-checklist.md"
