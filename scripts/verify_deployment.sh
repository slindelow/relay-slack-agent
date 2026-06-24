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
MCP_RESP=$(curl -s -X POST \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  --max-time 10 \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"verify","version":"0.1"}}}' \
  "$BASE/mcp-api/mcp" 2>/dev/null || echo "")
HEALTH_MCP=$(curl -s --max-time 5 "$BASE/health" | python3 -c "import sys,json; print(json.load(sys.stdin).get('mcp_mounted','?'))" 2>/dev/null || echo "?")
if echo "$MCP_RESP" | grep -q '"result"'; then
  echo "✅ MCP /mcp-api/mcp responding (mcp_mounted=$HEALTH_MCP)"
  PASS=$((PASS + 1))
else
  echo "❌ MCP /mcp-api/mcp not responding (mcp_mounted=$HEALTH_MCP)"
  echo "   Response: ${MCP_RESP:0:100}"
  FAIL=$((FAIL + 1))
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
echo ""
echo "--- MCP Client Config ---"
echo "Endpoint: $BASE/mcp-api/mcp (streamable HTTP, MCP 2024-11-05)"
echo "Add to claude.json: {\"relay\": {\"command\": \"uv\", \"args\": [\"run\", \"python\", \"-m\", \"relay.context.mcp_server\"]}}"
