# RELAY Reviewer Walkthrough

This guide walks a Slack App Marketplace reviewer through the full RELAY flow end-to-end using the pre-seeded sandbox workspace.

---

## Prerequisites

1. Install the RELAY Slack app in the reviewer sandbox workspace (`T_RELAY_DEMO`).
2. Seed the sandbox database:
   ```
   python scripts/seed_reviewer_sandbox.py --database-url $DATABASE_URL
   ```
3. The seed creates: 2 customer accounts, 2 Slack Connect channels, 3 open questions, 1 pending draft, and 2 resolved questions with knowledge entries.

---

## Step 1 — Install the app

Open the RELAY OAuth install link and authorise the app for the sandbox workspace.

**Expected:** RELAY App Home appears in the Slack sidebar showing connector status and an empty metrics section.

---

## Step 2 — Register a customer channel

In Slack, run:
```
/relay register #acme-corp-support "Acme Corp" enterprise @demo.csm
```

**Expected:** Ephemeral response confirms `#acme-corp-support` is registered for Acme Corp.

---

## Step 3 — Receive an SLA alert

The sandbox question `"Can you export our audit logs to CSV?"` is already past its SLA deadline. Within the next Celery beat cycle (≤60s), RELAY sends a DM alert card to the Demo CSM.

**Expected:** DM alert card shows question excerpt, SLA status (OVERDUE), and action buttons: **Claim**, **Snooze**, **Open Draft**.

---

## Step 4 — Claim the question

Click **Claim** in the DM alert card.

**Expected:** Ephemeral message confirms `"Claimed: Can you export our audit logs to CSV?"` The question state changes to `claimed`.

---

## Step 5 — Generate a draft

Click **Open Draft** in the DM alert card, or click **Generate Draft** in App Home next to the claimed question.

RELAY assembles evidence (knowledge entries + any connected sources), calls Claude to generate a draft, and opens a review modal.

**Expected:** Draft modal appears with: customer question excerpt, CRM context (tier, ARR, renewal date), suggested response text, confidence badge, source citations, and **Send**, **Regenerate**, **Discard** buttons.

---

## Step 6 — Approve and send the draft

Review the draft text (edit if needed), then click **Send**.

**Expected:** The approved response is posted to `#acme-corp-support` with the CSM's name in the footer. Question state changes to `resolved`. App Home impact metrics update.

---

## Step 7 — Search the knowledge base

Run `/relay ask audit log export` to test ad-hoc retrieval.

**Expected:** Ephemeral response lists the resolved question about audit logs as a `relay_memory` source with a brief excerpt.

---

## Step 8 — Check account pulse

Run `/relay pulse Acme Corp`.

**Expected:** Ephemeral response shows Acme Corp's open question count, 30-day SLA met rate, renewal date, ARR, and assigned CSM.

---

## Step 9 — Verify App Home metrics

Open the RELAY App Home tab.

**Expected:** App Home shows:
- **Impact metrics** section: SLA met rate, draft acceptance rate, median time-to-send.
- **Accuracy** section: correction rate for the past 7 days.
- **Source connectors** section (if any connected).

---

## Step 10 — Delete workspace data

Run `/relay delete-workspace-data` and confirm the modal.

**Expected:** A Celery task runs and deletes all workspace data. All tables for `T_RELAY_DEMO` are empty after completion. A final audit log entry with `event_type=workspace_deleted` is written before deletion.

---

## Verification commands

Check all data is removed after Step 10:
```sql
SELECT COUNT(*) FROM questions WHERE workspace_id = '<workspace_id>';
-- Expected: 0
SELECT event_type FROM audit_log ORDER BY created_at DESC LIMIT 1;
-- Expected: workspace_deleted
```
