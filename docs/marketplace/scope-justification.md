# Slack OAuth Scope Justification

RELAY requests the minimum Slack scopes needed to monitor registered Slack Connect customer channels, alert customer success owners, and post only human-approved responses.

## `groups:history`

RELAY reads message events in private Slack Connect channels where it has been installed and where an admin has registered the channel. This is required to detect unanswered customer questions and start the SLA workflow.

## `channels:history`

RELAY reads message events in public Slack Connect channels where it has been installed and where an admin has registered the channel. This is required for beta workspaces that use public shared customer channels. RELAY does not bulk ingest public channels; unregistered channels are ignored by the worker.

## `groups:read`

RELAY uses this scope to identify private channels the bot is a member of and to validate registered Slack Connect channels. It does not enumerate or ingest private channels that have not been registered for monitoring.

## `channels:read`

RELAY checks channel metadata during registration, including whether the bot is present and whether the channel is shared externally.

## `chat:write`

RELAY needs to post approved customer responses, App Home interactions, and operational notifications. Generated drafts are never posted to customer channels without human approval.

## `chat:write.customize`

When a CSM approves a draft, RELAY posts the reply to the customer channel under the approving CSM's own name and avatar (not RELAY's), so the customer experience is a normal message from their CSM rather than from a tool. RELAY is an internal co-pilot and is not surfaced to the customer.

## `im:write`

RELAY sends direct-message alert cards to customer success owners when a customer question is at risk of missing its SLA.

## `users:read`

RELAY resolves Slack user IDs into display names for alert cards, ownership assignment, and approval attribution.

## `commands`

RELAY registers `/relay` slash commands for channel registration, ad-hoc knowledge lookup, account pulse summaries, and administrative workflows.

## User scope: `search:read.public`

RELAY uses Slack Real-Time Search to retrieve relevant internal public-channel context on behalf of the CSM who explicitly enables Slack Search Context. Search results are used as internal evidence for drafts and `/relay ask`; RELAY does not continuously ingest or store public-channel history.

## User scope: `search:read.files`

RELAY includes Slack files in permission-aware Real-Time Search results so CSMs can find recent internal handoffs, snippets, and shared files relevant to customer questions. File search results are cited in internal review surfaces and are not copied into customer replies by default.

## User scope: `search:read.users`

RELAY allows Slack Real-Time Search to resolve user-related context returned by Slack search, such as author or owner information on relevant internal messages. RELAY does not use this scope to build a directory export.

## Optional Connector Integrations

GitHub, CRM, and future connector integrations are optional and are used only when a workspace admin configures that source. Connector content is scoped to the configured source and can be disconnected and purged independently. Google Drive/Docs setup is not exposed in the beta Slack UI until direct Google OAuth is ready.
