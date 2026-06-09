# Private Beta Acceptance Checklist

Use this checklist for the first friendly Slack Connect beta workspace. Keep the run manual until real Slack/AWS credentials are available in CI.

## Environment

- Beta API URL:
- Slack workspace:
- Slack Connect test channel:
- Customer test workspace/team:
- Operator:
- Date:

## Preflight

- [ ] `.venv/bin/python scripts/beta_preflight.py` reports all required checks as `PASS`.
- [ ] `curl $APP_BASE_URL/health` returns `status=ok`, `db=ok`, and `redis=ok`.
- [ ] `uv run celery -A relay.worker.celery_app.celery inspect ping --timeout=5` returns at least one worker.
- [ ] `KMS_PROVIDER=aws KMS_KEY_ID=... .venv/bin/python scripts/smoke_kms.py` prints `KMS smoke ok`.
- [ ] `.venv/bin/python scripts/beta_preflight.py --live` reports all required checks as `PASS`.
- [ ] Slack app manifest URLs match `APP_BASE_URL`.

## Install And Setup

- [ ] Visit `$APP_BASE_URL/`.
- [ ] Click `Add to Slack`.
- [ ] Complete Slack OAuth install.
- [ ] Open RELAY App Home.
- [ ] Run `/relay settings`.
- [ ] Confirm the installer is the first RELAY admin.
- [ ] Confirm `/relay settings` shows setup status and connector setup buttons.

## Account And Source Setup

- [ ] Connect HubSpot, or seed one test account if HubSpot is unavailable.
- [ ] Configure at least one source connector through `/relay settings`.
- [ ] Trigger connector sync from `/relay settings`.
- [ ] Confirm source sync status moves to `synced`.
- [ ] Run `/relay ask <known source question>` and confirm RELAY returns a relevant source.

## Slack Connect Flow

- [ ] Register the Slack Connect channel with `/relay register #channel Account Name enterprise @owner`.
- [ ] Post a customer-like question from the external/customer side.
- [ ] Confirm RELAY ingests the message and creates or detects an open question.
- [ ] Trigger or wait for SLA poller alert.
- [ ] CSM receives alert DM.
- [ ] CSM clicks `Claim`.
- [ ] CSM clicks/generates a draft from App Home.
- [ ] Draft modal opens with evidence.
- [ ] CSM approves and sends.
- [ ] RELAY posts the approved response to the customer channel.
- [ ] Response is not posted before human approval.
- [ ] Approved response is indexed as memory.

## Deletion And Cleanup

- [ ] Use App Home or `/relay settings` to purge the test source connector.
- [ ] Run `/relay delete-workspace-data` in the beta workspace.
- [ ] Confirm deletion job completes.
- [ ] Confirm no tenant data remains for the workspace in DB verification.
- [ ] If uninstalling, confirm `app_uninstalled` revokes active workspace tokens and enqueues deletion.

## Follow-Ups

Record every failed step in `docs/HANDOFF.md` with:

```markdown
- Beta acceptance issue:
  - Step:
  - Expected:
  - Actual:
  - Logs/IDs:
  - Owner:
  - Next action:
```
