# Slack OAuth Scope Justification

RELAY requests the minimum Slack scopes needed to monitor registered Slack Connect customer channels, alert customer success owners, and post only human-approved responses.

## `groups:history`

RELAY reads message events in private Slack Connect channels where it has been installed and where an admin has registered the channel. This is required to detect unanswered customer questions and start the SLA workflow. RELAY does not request `channels:history`, so internal public-channel history is not monitored.

## `groups:read`

RELAY uses this scope to identify private channels the bot is a member of and to validate registered Slack Connect channels. It does not enumerate or ingest private channels that have not been registered for monitoring.

## `channels:read`

RELAY checks channel metadata during registration, including whether the bot is present and whether the channel is shared externally. It does not request public-channel message history.

## `chat:write`

RELAY needs to post approved customer responses, App Home interactions, and operational notifications. Generated drafts are never posted to customer channels without human approval.

## `im:write`

RELAY sends direct-message alert cards to customer success owners when a customer question is at risk of missing its SLA.

## `users:read`

RELAY resolves Slack user IDs into display names for alert cards, ownership assignment, and approval attribution.

## `commands`

RELAY registers `/relay` slash commands for channel registration, ad-hoc knowledge lookup, account pulse summaries, and administrative workflows.

## Optional Connector Scopes

Google Drive, GitHub, CRM, and future connector scopes are optional and are requested only when a workspace admin configures that connector. Connector content is scoped to the configured source and can be disconnected and purged independently.
