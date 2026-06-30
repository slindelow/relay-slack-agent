# RELAY — Demo Recording Script

A tight, repeatable walkthrough for the submission video. Target length: **2–3 minutes**.
Record in the "RELAY Beta" Slack workspace against the live Railway deploy
(`https://web-production-acd3.up.railway.app`).

> ⚠️ **Record BEFORE running checklist Steps 13 (delete-workspace-data) and 14
> (uninstall).** Those wipe the data this demo depends on.

---

## Pre-flight (do this 5 min before recording)

1. **Health is green**
   ```bash
   curl -s https://web-production-acd3.up.railway.app/health
   # → {"status":"ok","service":"relay","db":"ok","redis":"ok"}
   ```
2. **Worker + beat are running** — the SLA poller fires every 60s and the
   draft generator runs in the worker. Confirm in Railway logs that the worker
   shows `celery@... ready` and beat is scheduling `relay.poll_sla`.
3. **HubSpot is synced** — click **Sync HubSpot** in `/relay settings`, or just
   confirm `/relay pulse Lindelow Partners` shows `ARR: $250`.
4. **Reset the demo question (optional but recommended)** — so you have a clean
   "open" question to show, post a fresh customer message right before recording
   rather than reusing a resolved one.
5. **Reinstall the Slack app** if you want **Send** to post as the CSM's name +
   avatar (grants `chat:write.customize`). If you skip this, Send still works —
   it posts a clean plain message with no RELAY branding.

---

## The recording (full loop)

**Scene 1 — The problem (10s).**
Show the registered Slack Connect customer channel. Voiceover: *"Customer
questions in Slack Connect channels get missed. RELAY watches them, enforces
SLA, and drafts cited replies — with a human always in the loop."*

**Scene 2 — A customer asks a question (20s).**
In the registered channel, post as the customer:
> "Hey — when does our contract renew, and is SSO included in the enterprise plan?"

Within ~30s, RELAY classifies it and the on-call CSM gets a **DM alert** card.
Show the DM landing. Voiceover: *"RELAY detected an unanswered question and
alerted the account owner — no one had to be watching."*

**Scene 3 — SLA visibility via pulse (20s).**  *(this is checklist Step 8)*
Run:
```
/relay pulse Lindelow Partners
```
Show the response: account tier, **ARR from HubSpot**, owner, SLA rate, and the
new **Open questions** list — each question with an urgency dot and a
**"waiting <time>"** label (e.g. *"waiting 2m"*). Voiceover: *"At a glance, the
CSM sees the account's value and exactly how long each question has been waiting
— before the SLA is breached."*

**Scene 4 — Claim → cited draft (30s).**
In the DM alert, click **Claim**. RELAY auto-generates a draft (Sonnet 4.6 via
the MCP context server) and surfaces it in the App Home **"Drafts Ready for
Review"** section. Open it. Voiceover: *"One click claims the question and
generates a draft grounded in CRM, docs, and GitHub context — every claim cites
its sources."* Show the citation(s) in the draft modal.

**Scene 5 — Human approval → send (20s).**
Optionally edit the draft, then click **Send**. The reply posts into the
customer channel (as the CSM if `chat:write.customize` is granted). The question
flips to **resolved** and the SLA timer stops. Voiceover: *"Nothing reaches the
customer without human approval. Approve, and RELAY posts it and remembers the
resolution for next time."*

**Scene 6 — Knowledge recall (15s, optional).**
Run:
```
/relay ask refund policy
```
Show a cited answer pulled from the indexed GitHub knowledge. Voiceover:
*"RELAY also answers internal questions from your connected knowledge sources."*

**Close (10s).**
Voiceover: *"RELAY — a Slack-native customer-success agent. Detect, draft, and
resolve, with a human in the loop."*

---

## Checklist Step 8 — explicit verification (for the sign-off table)

1. Complete Step 7 (post a customer question; confirm the CSM DM alert arrives).
2. **Do not claim it.** Wait ~2 minutes.
3. Run `/relay pulse Lindelow Partners`.
4. **Verify:** the **Open questions** list shows the question with a
   **"waiting <time>"** age that increases over time. ✅
5. **Verify:** no second/escalation DM fires in that window. By design the first
   alert sets the next alert ~240 min out (escalation window), so no premature
   breach alert can fire in a 2-minute window. ✅

> SLA windows: default response 60 min, escalation 240 min (in
> `relay/sla/poller.py`; overridable per-account via an `SlaPolicy` row). A fresh
> question has `next_alert_at = NULL`, so the first poll cycle (≤60s) sends the
> initial alert, then schedules the next one 240 min later.

---

## After recording

Run the destructive steps last, in order:
- **Step 13** — `/relay delete-workspace-data` → confirm full purge + token revoke.
- **Step 14** — Remove RELAY from the workspace → confirm `app_uninstalled`
  handler fires and the bot token is revoked.

Then finalize the Devpost writeup.
