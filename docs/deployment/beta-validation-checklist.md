# Beta Validation Checklist

> Current private-beta operators should use `docs/deployment/private-beta-acceptance.md` first. This older checklist remains as the detailed scenario reference.

Run this end-to-end flow against a fresh workspace after every beta deploy. All 14 steps must complete without any database intervention.

---

## Pre-conditions

- Deployed stack is running (`curl $APP_BASE_URL/health` returns `{"status":"ok","db":"ok","redis":"ok"}`)
- Celery worker and beat are running (`celery -A relay.worker.celery_app inspect ping` succeeds)
- A test Slack workspace is available (not the production workspace)
- Test HubSpot sandbox account is available

---

## Step 1 — Install via OAuth

1. Open `$APP_BASE_URL/` in a browser
2. Click **Add to Slack**
3. Complete the Slack OAuth flow (authorize in the test workspace)
4. **Verify:** `workspaces` table has a new row for the test workspace
5. **Verify:** The installing user has `relay_role = 'admin'` in the `users` table
6. **Verify:** `/relay help` responds in the test workspace

---

## Step 2 — App Home: 1/4 complete

1. Open the RELAY app home tab in Slack
2. **Verify:** Setup checklist shows exactly one item checked: "RELAY admin configured"
3. Remaining items show as incomplete: channel, CRM, knowledge source

---

## Step 3 — Register a channel

1. Invite RELAY to a test Slack Connect channel (or a regular channel for testing)
2. Run `/relay register #test-channel TestCo`
3. **Verify:** Command responds with confirmation
4. **Verify:** `monitored_channels` table has a new row for the channel
5. Open App Home — **Verify:** Setup checklist now shows 2/4 complete

---

## Step 4 — Connect HubSpot

1. In App Home or via `/relay settings`, click **Connect HubSpot**
2. Complete the HubSpot OAuth flow
3. **Verify:** OAuth redirect returns to RELAY and shows success message
4. Trigger a manual sync (or wait for the scheduled task)
5. **Verify:** `customer_accounts` table has rows with `crm_provider = 'hubspot'`
6. Open App Home — **Verify:** Setup checklist now shows 3/4 complete

---

## Step 5 — Connect a knowledge source

1. In `/relay settings`, click **Connect GitHub**
2. Enter a GitHub personal access token for a repo with documentation
3. Submit the modal
4. **Verify:** `source_connectors` table has a new row with `connector_type = 'github'`
5. Wait for the sync task to complete (App Home shows sync status)
6. **Verify:** `knowledge_entries` table has rows from the synced repo
7. Open App Home — **Verify:** Setup checklist now shows 4/4 complete (all green ✅)

---

## Step 6 — Full setup confirmed

1. Open App Home
2. **Verify:** Header reads ":tada: Setup complete" (not "*Setup checklist*")
3. **Verify:** All four checklist items are checked

---

## Step 7 — Customer question flow

1. Post a message in the registered test channel that reads like a customer question
   - Example: "Hey, when does my contract renew and what's included in the enterprise plan?"
2. **Verify:** Within 30 seconds, a `questions` row appears with `status = 'open'`
3. **Verify:** The on-call CSM receives a DM alert from RELAY

---

## Step 8 — SLA timer

1. After step 7, wait 2 minutes without claiming the question
2. Run `/relay pulse TestCo`
3. **Verify:** The pulse response shows the open question with time-since-posted
4. **Verify:** No SLA breach alert fires prematurely (breach threshold is configured in `.env`)

---

## Step 9 — Claim and draft

1. In the CSM DM alert, click **Claim**
2. **Verify:** The question status changes to `claimed` in the DB
3. **Verify:** A draft modal opens within 5 seconds with:
   - A suggested response
   - At least one evidence source cited
   - Edit and Send buttons

---

## Step 10 — Send response

1. Edit the draft if desired
2. Click **Send**
3. **Verify:** The response is posted in the test channel as the RELAY bot
4. **Verify:** The question status changes to `resolved`
5. **Verify:** SLA timer stops

---

## Step 11 — Knowledge search

1. Run `/relay ask refund policy`
2. **Verify:** RELAY returns a relevant result with a source citation
3. Run `/relay ask` with a query that has no match
4. **Verify:** RELAY responds gracefully ("I couldn't find anything relevant")

---

## Step 12 — Account pulse

1. Run `/relay pulse TestCo`
2. **Verify:** Response includes:
   - Account name and tier
   - ARR figure (from HubSpot sync)
   - Open question count
   - SLA compliance rate

---

## Step 13 — Workspace deletion

1. Run `/relay delete-workspace-data` in Slack
2. **Verify:** RELAY sends a confirmation prompt
3. Confirm the deletion
4. **Verify:** All workspace data is purged (workspaces, users, channels, questions, knowledge entries)
5. **Verify:** Bot token is revoked

---

## Step 14 — Uninstall

1. Remove RELAY from the test workspace via Slack's app settings
2. **Verify:** The `app_uninstalled` event handler fires
3. **Verify:** Bot token row is deleted or marked revoked in `workspace_tokens`

---

## Classifier Threshold Validation

After collecting data from 2+ beta workspaces (minimum 200 classified messages), check precision and recall:

```bash
uv run python scripts/eval_classifier.py --workspace-id <id>
```

Target thresholds (adjust `.env` if below target):
- `CLASSIFIER_OPEN_THRESHOLD=0.85` → precision ≥ 0.80
- `CLASSIFIER_CANDIDATE_THRESHOLD=0.60` → recall ≥ 0.70

Document the threshold decision in `docs/HANDOFF.md` with the evaluation date and sample size.

---

## Sign-off

| Step | Pass | Tested By | Date | Notes |
|------|------|-----------|------|-------|
| 1 — Install | ✅ PASS | sofialindelow | 2026-06-10 | OAuth install completed into "RELAY Beta" workspace. Redirect URL working. |
| 2 — App Home 1/4 | ✅ PASS | sofialindelow | 2026-06-10 | App Home showed 1/4 setup items complete (admin configured). |
| 3 — Channel registered | ✅ PASS | sofialindelow | 2026-06-24 | `/relay register #test-customer TestCo enterprise` → "Channel #C0B9F2Z6BSA registered for account 'TestCo' (tier: enterprise)". Required two fixes: (1) enable "Escape channels, users, and links" on the `/relay` slash command in Slack app settings; (2) parser fix `1c27eeb` to accept escaped channel mention `<#C123>` without `\|name` suffix. |
| 4 — HubSpot connected | ✅ PASS | sofialindelow | 2026-06-29 | HubSpot public (OAuth) app created via `hs project create`, `HUBSPOT_CLIENT_ID/SECRET/REDIRECT_URI` set on Railway web+worker, developer Acceptable Use Policy signed, OAuth connect completes from `/relay settings` → `customer_accounts` populated with `crm_provider='hubspot'`. Required fixes: connect button now passes `team_id/user_id` so it works from a Slack URL button (`1fb9cb3`); env var was misnamed `HUBSPOT_REDIRECT_URL` → `HUBSPOT_REDIRECT_URI`. |
| 5 — Knowledge source | ✅ PASS | sofialindelow | 2026-06-24 | GitHub connector (`slindelow/relay-slack-agent`) synced successfully (`sync_connector: synced`, no errors). Fixes required: enable Slack **Interactivity** (`/slack/events`) for connector buttons; worker event-loop crash (`cc3f63d`, NullPool); embedding dim 1536→1024 for voyage-3 (`0772760`, migration 0011); and **adding a Voyage payment method** to lift the free-tier 3 RPM rate limit (200M free tokens still apply, so $0). |
| 6 — Setup complete | ✅ PASS | sofialindelow | 2026-06-29 | All four core setup items green in `/relay settings`: admin, channel, HubSpot CRM, knowledge source. (Slack Search context is an optional 6th item, not required for core setup.) |
| 7 — Question classified | ✅ PASS | sofialindelow | 2026-06-24 | Customer message in #test-customer → classified → question created (`/relay pulse TestCo` shows 1 open) → CSM DM alert delivered. Required fixes: worker event-loop (`cc3f63d`), model IDs → Haiku 4.5/Sonnet 4.6 (`d5bf4a6`), assign account owner via `/relay register … @owner`, and enable Slack **Messages Tab** (was disabled → `messages_tab_disabled` blocked DMs). `PYTHONPATH=/app` is now exported by `scripts/entrypoint.sh` (2026-06-25). |
| 8 — SLA timer | ⏳ PENDING | — | — | Wait 2min after step 7; `/relay pulse TestCo`; no premature breach alert. |
| 9 — Claim and draft | ✅ PASS | sofialindelow | 2026-06-25 | **Claim now auto-generates the draft** (`7ca0926`) via the MCP `draft_generation` tool → Sonnet 4.6. Draft surfaces in the App Home **"Drafts Ready for Review"** section (`f1152d9`) with a working **Review draft** button (`36bb082`); claim/generate confirmations point to the Home tab (`7cf92c6`). Draft content is now an **always-sendable reply** — a safe holding response when evidence is thin, not a "Cannot Draft" brief (`309d87b`). |
| 10 — Send response | ✅ PASS | sofialindelow | 2026-06-25 | Send posts the reply into #test-customer **as the CSM (name + avatar), with zero RELAY branding** via `chat:write.customize` (`e87fc5e`; needs app reinstall for the scope) and resolves the question. Graceful fallback to a plain post (still no RELAY wording) if the scope isn't granted. |
| 11 — Knowledge search | ✅ PASS | sofialindelow | 2026-06-24 | `/relay ask …` returns results with source citations from the indexed GitHub repo knowledge. Confirmed retrieval pulls from concrete indexed content. |
| 12 — Account pulse | ✅ PASS | sofialindelow | 2026-06-29 | `/relay pulse Lindelow Partners` renders the account detail with tier, owner, and **ARR: $250** sourced from the HubSpot sync. Required fixes: map `annualrevenue` → `account.arr` (`42ae732`); paginate the company fetch so >100 companies sync (`c15a275`); guard ARR against Numeric(12,2) overflow so a $134B/$403B placeholder can't roll back the whole sync (`b121a34`). Added a manual **Sync HubSpot** button + 6-hourly auto-sync (`0f15f5f`). |
| 13 — Workspace deletion | ⏳ PENDING | — | — | `/relay delete-workspace-data` → confirm → verify full purge and token revoke. |
| 14 — Uninstall | ⏳ PENDING | — | — | Remove app from Slack workspace → verify `app_uninstalled` handler + token revoked. |

---

## Pre-validation Status (as of 2026-06-22)

### ✅ Deployment Live

```
curl https://web-production-acd3.up.railway.app/health
→ {"status":"ok","service":"relay","db":"ok","redis":"ok"}
```

FastAPI web service, PostgreSQL (pgvector), and Redis are all healthy.

### ✅ OAuth Redirect URL Registered

Steps 1 and 2 were confirmed completed on 2026-06-10 — the OAuth install flow completed successfully into the "RELAY Beta" workspace, which confirms `https://web-production-acd3.up.railway.app/slack/oauth_redirect` is registered in the Slack app settings.

### ⏳ Steps 3-14: Require Human Slack Interaction

Steps 3-14 cannot be automated — they require a human to interact with the live Slack workspace. Resume from step 3:

**Minimum Railway env vars to set before steps 4-12:**
```
HUBSPOT_CLIENT_ID=<from HubSpot developer account>
HUBSPOT_CLIENT_SECRET=<from HubSpot developer account>
HUBSPOT_REDIRECT_URI=https://web-production-acd3.up.railway.app/hubspot/oauth_redirect
VOYAGE_API_KEY=<from dash.voyageai.com>
```

**To add these via Railway CLI:**
```bash
railway variables set HUBSPOT_CLIENT_ID=<value> --service web
railway variables set HUBSPOT_CLIENT_SECRET=<value> --service web
railway variables set HUBSPOT_REDIRECT_URI=https://web-production-acd3.up.railway.app/hubspot/oauth_redirect --service web
railway variables set VOYAGE_API_KEY=<value> --service web
railway variables set VOYAGE_API_KEY=<value> --service worker
```

**Resume from:** Open the "RELAY Beta" workspace in Slack → invite RELAY to a test channel → `/relay register #test-channel TestCo`
