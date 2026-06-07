# RELAY — Slack OAuth Scope Justification

This document provides justification for each OAuth scope requested by the RELAY Slack app, as required for Slack App Marketplace submission.

---

## `groups:history`

**Data accessed:** Message content and metadata in private channels (Slack Connect customer channels) where the bot has been installed.

**Why RELAY needs it:** RELAY's core function is detecting unanswered customer questions in Slack Connect channels. Without read access to channel history, RELAY cannot inspect messages to determine whether a question has been asked, whether it has been answered, or whether it is approaching SLA. This is the fundamental capability the product is built on.

**Consequence of denial:** RELAY cannot function at all. No question detection, no SLA tracking, no draft generation.

---

## `groups:read`

**Data accessed:** List of private channels the bot is a member of, including channel name and metadata.

**Why RELAY needs it:** When a CSM registers a channel with `/relay register`, RELAY needs to verify the bot is a member of the specified channel and store the channel ID for future message monitoring. `groups:read` is also used to display registered channels in App Home.

**Consequence of denial:** The `/relay register` command cannot verify channel membership, making registration unreliable.

---

## `channels:read`

**Data accessed:** List of public channels and their basic metadata (name, ID, member count).

**Why RELAY needs it:** During channel registration, RELAY checks whether the channel being registered is a public or private channel so it can route monitoring correctly. Some Slack Connect channels are set up as public channels.

**Consequence of denial:** Registration may fail for public Slack Connect channels.

---

## `chat:write`

**Data accessed:** Permission to post messages to channels the bot is a member of.

**Why RELAY needs it:** When a CSM approves a draft in RELAY, the approved response is posted to the customer channel using `chat:write`. RELAY also posts alert DM cards to CSMs using this scope (for direct message channels the bot is already in). No message is ever sent without explicit CSM approval.

**Consequence of denial:** RELAY cannot deliver approved responses to customers or send alert notifications.

---

## `im:write`

**Data accessed:** Permission to open and post direct messages to users.

**Why RELAY needs it:** When a question enters SLA risk (approaching deadline, escalation needed), RELAY sends a DM alert card to the assigned CSM or team members. These DMs contain a summary of the at-risk question and action buttons (Claim, Snooze, View Draft).

**Consequence of denial:** CSMs do not receive SLA alert notifications. The SLA management feature is disabled.

---

## `users:read`

**Data accessed:** Slack user profile data (display name, real name, email) for users in the workspace.

**Why RELAY needs it:** Alert DM cards display the assigned CSM's name. The App Home pulse view shows owner and backup owner names for customer accounts. RELAY also uses `users:read` to resolve Slack user IDs to display names when registering accounts and displaying audit history.

**Consequence of denial:** User names display as raw Slack user IDs (e.g., `U01ABC123`) instead of human-readable names.

---

## `commands`

**Data accessed:** Permission to register slash commands in the workspace.

**Why RELAY needs it:** RELAY's primary CSM interface is the `/relay` slash command, which routes subcommands including `/relay register`, `/relay ask`, `/relay pulse`, and `/relay delete-workspace-data`. Without this scope, none of the slash commands are available.

**Consequence of denial:** No slash command interface. CSMs cannot register channels, search knowledge, or manage workspace data.

---

## Notes

- **No `channels:history` scope** — RELAY only monitors registered Slack Connect customer channels (private channels), not internal workspace channels. `channels:history` would allow reading all public channel history, which RELAY does not need and does not request.
- **Connector scopes are optional** — Google Drive OAuth and GitHub token scopes are requested separately during connector setup, not at initial installation. Users who do not configure connectors are never asked for these permissions.
