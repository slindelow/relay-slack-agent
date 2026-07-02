# RELAY Marketplace Reviewer Walkthrough

This walkthrough uses the sandbox created by `scripts/seed_reviewer_sandbox.py`.

## Sandbox Data

- Workspace: `RELAY Reviewer Sandbox` (`T_RELAY_REVIEW`)
- Reviewer/admin user: `UREVIEWADMIN`
- Enterprise account: `Acme Enterprise`, channel `ext-acme-support` (`C_REVIEW_ACME`)
- Starter account: `Beta Starter`, channel `ext-beta-support` (`C_REVIEW_BETA`)
- Seeded queue:
  - Past-SLA open question: `SSO certificate rotation steps`
  - Snoozed open question: `Audit export API availability`
  - Claimed question: `Add teammates to pilot workspace`
  - Pending draft: response for `SSO certificate rotation steps`
  - Resolution memory: `Data retention wording` and `Customer guest invite checklist`

## Setup

1. Run the latest migrations.
2. Seed the sandbox:

```bash
.venv/bin/python scripts/seed_reviewer_sandbox.py
```

3. Install the RELAY Slack app into the reviewer workspace.
4. Confirm the app has the documented scopes in `docs/marketplace/scope-justification.md`.

Expected result: the app installs without requesting internal-channel history and the sandbox workspace exists with the stable IDs above.

## Register A Slack Connect Channel

In Slack, run:

```text
/relay add #ext-acme-support Acme Enterprise enterprise @UREVIEWADMIN
```

Expected result: RELAY replies ephemerally that `ext-acme-support` is registered to `Acme Enterprise`.

## Review The Queue

Open the RELAY App Home.

Expected result:
- `Acme Enterprise` appears with a past-SLA open question.
- `Beta Starter` appears with a claimed pilot-workspace question.
- Impact and accuracy sections render without errors.
- Connected sources, when configured, expose `Disconnect + Purge`.

## Alert, Claim, And Snooze

1. Trigger the SLA poller in the worker environment.
2. Open the DM alert for `SSO certificate rotation steps`.
3. Click `Claim`.

Expected result:
- The alert card shows the Acme question, urgency, and account context.
- Claiming updates the question state to claimed and records a question event.

For the seeded `Audit export API availability` question, verify that the active snooze suppresses immediate escalation until `snoozed_until`.

## Draft And Approve

1. Open the pending draft for `SSO certificate rotation steps`.
2. Review the cited evidence bundle.
3. Click `Send`.

Expected result:
- RELAY posts the approved response into the original Slack thread.
- The draft status moves to `sent`.
- A sent response can later be indexed as approved memory.

## Ask Memory

Run:

```text
/relay ask What should we say about data retention?
```

Expected result: RELAY returns the seeded `Data retention wording` memory entry with source context.

## Account Pulse

Run:

```text
/relay pulse Acme Enterprise
```

Expected result: RELAY returns Acme account health, tier, ARR, renewal proximity, owner/backup context, and current open questions.

## Connector Purge

If a source connector is configured in the sandbox, open App Home and click `Disconnect + Purge`.

Expected result: RELAY asks for confirmation, then removes derived `source_documents` and `knowledge_chunks` for that connector and marks it disconnected.

## Workspace Deletion

Run:

```text
/relay delete-workspace-data
```

Confirm the modal.

Expected result:
- RELAY enqueues a workspace deletion job.
- Active workspace tokens are revoked on uninstall.
- Workspace-scoped rows are removed by the deletion worker.
- A `workspace_deleted` audit entry is written before the workspace row is deleted.

## Public Compliance Pages

Open these unauthenticated URLs:

- `/privacy`
- `/terms`
- `/sub-processors`
- `/health`

Expected result:
- Legal pages return `200`.
- `/health` returns dependency statuses for `db` and `redis`, and returns `503` if either dependency is unavailable.
