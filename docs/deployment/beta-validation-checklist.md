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
| 1 — Install | ⏳ BLOCKED | — | — | Requires OAuth redirect URL added to Slack app settings (see below) |
| 2 — App Home 1/4 | ⏳ BLOCKED | — | — | Depends on step 1 |
| 3 — Channel registered | ⏳ BLOCKED | — | — | Depends on step 1 |
| 4 — HubSpot connected | ⏳ BLOCKED | — | — | Depends on step 1 |
| 5 — Knowledge source | ⏳ BLOCKED | — | — | Depends on step 1 |
| 6 — Setup complete | ⏳ BLOCKED | — | — | Depends on steps 1-5 |
| 7 — Question classified | ⏳ BLOCKED | — | — | Depends on step 1 |
| 8 — SLA timer | ⏳ BLOCKED | — | — | Depends on step 7 |
| 9 — Claim and draft | ⏳ BLOCKED | — | — | Depends on step 7 |
| 10 — Send response | ⏳ BLOCKED | — | — | Depends on step 9 |
| 11 — Knowledge search | ⏳ BLOCKED | — | — | Depends on step 1 |
| 12 — Account pulse | ⏳ BLOCKED | — | — | Depends on steps 1 + 4 |
| 13 — Workspace deletion | ⏳ BLOCKED | — | — | Depends on step 1 |
| 14 — Uninstall | ⏳ BLOCKED | — | — | Depends on step 1 |

---

## Pre-validation Status (as of 2026-06-22)

### ✅ Deployment Live

```
curl https://web-production-acd3.up.railway.app/health
→ {"status":"ok","service":"relay","db":"ok","redis":"ok"}
```

FastAPI web service, PostgreSQL (pgvector), and Redis are all healthy.

### ❌ BLOCKER: OAuth Redirect URL Not Registered

The Slack app manifest in `slack-app-manifest.yaml` previously had placeholder URLs (`relay-beta.example.com`). The manifest has been updated to the correct Railway URLs, but the **Slack app settings at api.slack.com/apps must be updated manually**:

**Required action (human — needs Slack app admin access):**

1. Generate the deployment manifest:
   ```bash
   ./scripts/configure-manifest.sh https://web-production-acd3.up.railway.app
   # Outputs: slack-app-manifest-generated.yaml
   ```

2. Go to https://api.slack.com/apps → select the RELAY Beta app → **App Manifest**
3. Paste the contents of `slack-app-manifest-generated.yaml` and click **Save Changes**

This updates all URLs in one step: slash command URL, OAuth redirect URLs (including `/slack/search/oauth_redirect`), and event subscription/interactivity request URLs.

**Once the Slack app is updated**, resume from Step 1 of the checklist above using the Railway install URL:
`https://web-production-acd3.up.railway.app/`
