# RELAY Beta User Guide

Welcome to the RELAY private beta. This guide is written for CS team admins — no technical background needed.

---

## What RELAY does

RELAY watches your customer Slack Connect channels and automatically detects unanswered questions. When a customer asks something, RELAY notifies your team, helps draft a response using your internal knowledge, and lets a human review and send it — all without leaving Slack.

The goal: no customer question goes unanswered, and your team spends less time searching for the right answer.

---

## Installing RELAY

1. Click the **Add to Slack** link provided by your RELAY contact
2. You'll be taken to Slack's authorization page — click **Allow**
3. That's it. RELAY is now installed in your workspace

The person who installs RELAY becomes the first admin automatically.

---

## Initial setup (4 steps)

Open the RELAY app in Slack (find it in your Apps sidebar). You'll see a setup checklist:

### 1. Admin configured ✅
This is done automatically when you install RELAY.

To give another team member admin access, have them message RELAY directly or ask your RELAY contact.

### 2. Register a customer channel

Run this command from Slack's main message box:

```
/relay add #channel-name CompanyName enterprise @owner
```

Replace `#channel-name` with the actual Slack channel, `CompanyName` with the customer's name, and `@owner` with the account owner (e.g., `/relay add #acme-support Acme Corp enterprise @sofia`).

RELAY will confirm when the channel is registered.

### 3. Connect HubSpot

In the RELAY app home, click **Connect HubSpot** and follow the authorization flow. This lets RELAY look up account details (ARR, renewal date, tier) when a question comes in.

If you don't use HubSpot, you can skip this step for now — RELAY will still work without it.

### 4. Connect a knowledge source

Go to `/relay settings` and click **Connect GitHub**.

- **GitHub:** Paste a personal access token and the documentation repositories RELAY should index.

Once connected, RELAY syncs your content and uses it to draft responses. Google Drive/Docs setup is intentionally hidden in this beta until direct Google OAuth is ready.

### Optional: enable Slack Search

In `/relay settings`, click **Enable Slack Search** if you want RELAY to use permission-aware internal Slack search for your user. This helps drafts and `/relay ask` find recent internal context without bulk-ingesting public-channel history.

---

## Day-to-day use

### When a customer asks a question

RELAY detects the question and sends you (or the on-call CSM) a DM:

> *"Customer question in #acme-support — 'When does our contract renew?' — 2 minutes ago"*

You'll see two buttons: **Claim** and **Ignore**.

### Claiming a question

Click **Claim** to take ownership. RELAY will open a draft response for you to review:

- The suggested reply is based on your knowledge sources
- You'll see evidence links showing where the answer came from
- Edit the draft directly in the modal, then click **Send**

RELAY posts the response in the channel as the bot. The question is marked resolved.

### If no one claims a question

RELAY tracks how long each question has been open. If it crosses your SLA threshold, the team gets an alert.

---

## Useful commands

| Command | What it does |
|---------|-------------|
| `/relay help` | Shows all available commands |
| `/relay ask <question>` | Search your knowledge base directly |
| `/relay pulse <company>` | Account digest: open questions, SLA status, ARR |
| `/relay add #channel Company enterprise @owner` | Add a channel to monitoring |
| `/relay settings` | Manage connectors and team settings |

### Examples

```
/relay ask what is our refund policy
/relay pulse Acme Corp
/relay add #beta-customer-support BetaCo enterprise @sofia
```

---

## Adding team members

Currently, CSMs are added to RELAY when they first interact with it (e.g., claim a question or run a command). Admin roles must be assigned manually — message your RELAY contact to promote someone to admin.

---

## Checking on the setup

Run `/relay settings` at any time to see:
- Which channels are registered
- Which knowledge sources are connected and when they last synced
- HubSpot connection status
- Whether Slack Search context is enabled for you

The App Home tab also shows a live setup checklist and your team's open question queue.

---

## Getting help or reporting a problem

If something isn't working:

1. Check the RELAY App Home — error messages appear there for failed syncs
2. Run `/relay help` to confirm the bot is responding
3. Email **support@relay.example.com** with:
   - Your Slack workspace name
   - What you expected to happen
   - What actually happened (a screenshot helps)

---

## Removing RELAY

To remove RELAY from your workspace:

1. Go to **Slack → Settings → Manage apps**
2. Find RELAY and click **Remove**

This revokes RELAY's access immediately. All stored data can also be deleted on request — run `/relay delete-workspace-data` before uninstalling if you want to erase all records.

---

## Privacy and data

RELAY stores:
- Customer messages that are identified as questions (not all messages)
- Your team's responses and draft history
- Knowledge content you explicitly sync (GitHub repositories in this beta)
- Account data from HubSpot (name, ARR, tier)

RELAY does **not** store full message history. Only messages classified as customer questions are retained.

For the full privacy policy, visit <https://web-production-acd3.up.railway.app/privacy>.
