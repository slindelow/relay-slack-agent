"""Handler logic for the /relay settings subcommand."""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select

from relay.config import get_settings
from relay.context.slack_rts import revoke_user_search_tokens, slack_search_status
from relay.crypto import encrypt_token, ensure_workspace_dek, kms_provider_from_settings
from relay.db.models import CrmConnection, MonitoredChannel, SourceConnector, User, Workspace
from relay.db.session import get_session

logger = logging.getLogger(__name__)


@dataclass
class SettingsStatus:
    installed: bool
    admin_count: int = 0
    bootstrapped_admin: bool = False
    channel_count: int = 0
    crm_connected: bool = False
    source_count: int = 0
    slack_search_connected: bool = False
    app_base_url: str = ""
    slack_team_id: str = ""
    slack_user_id: str = ""
    connector_rows: list[Any] = field(default_factory=list)


def _mark(done: bool) -> str:
    return ":white_check_mark:" if done else ":white_circle:"


def build_settings_blocks(status: SettingsStatus) -> list[dict]:
    """Build the setup status blocks shown by /relay settings."""
    install_line = f"{_mark(status.installed)} Slack app installed"
    admin_line = f"{_mark(status.admin_count > 0)} First RELAY admin configured"
    channel_line = f"{_mark(status.channel_count > 0)} Customer Slack Connect channel registered"
    crm_line = f"{_mark(status.crm_connected)} HubSpot connected"
    source_line = f"{_mark(status.source_count > 0)} Knowledge source connected"
    slack_search_line = f"{_mark(status.slack_search_connected)} Slack Search context enabled"

    help_text = (
        "*Private beta setup*\n"
        f"{install_line}\n"
        f"{admin_line}\n"
        f"{channel_line}\n"
        f"{crm_line}\n"
        f"{source_line}\n"
        f"{slack_search_line}"
    )
    search_connect_url = _slack_search_connect_url(status)

    actions = [
        {
            "type": "button",
            "text": {"type": "plain_text", "text": "Connect HubSpot"},
            "url": _hubspot_connect_url(status),
        },
        *(
            [{
                "type": "button",
                "text": {"type": "plain_text", "text": "Sync HubSpot"},
                "action_id": "relay_sync_hubspot",
                "value": "hubspot",
            }]
            if status.crm_connected
            else []
        ),
        {
            "type": "button",
            "text": {"type": "plain_text", "text": "Connect GitHub"},
            "action_id": "relay_setup_github_connector",
            "value": "github",
        },
        {
            "type": "button",
            "text": {"type": "plain_text", "text": "Connect Google Drive"},
            "action_id": "relay_setup_google_drive_connector",
            "value": "google_drive",
        },
        {
            "type": "button",
            "text": {"type": "plain_text", "text": "Enable Slack Search"},
            "url": search_connect_url,
        },
        *(
            [{
                "type": "button",
                "text": {"type": "plain_text", "text": "Disconnect Slack Search"},
                "action_id": "relay_disconnect_slack_search",
                "value": "disconnect",
                "style": "danger",
            }]
            if status.slack_search_connected
            else []
        ),
        {
            "type": "button",
            "text": {"type": "plain_text", "text": "Open install page"},
            "url": status.app_base_url.rstrip("/") or "https://relay.example.com",
        },
    ]

    blocks = [
        {"type": "section", "text": {"type": "mrkdwn", "text": "*RELAY settings*"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": help_text}},
        *(
            [{
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": ":key: You are now the first RELAY admin for this workspace.",
                },
            }]
            if status.bootstrapped_admin
            else []
        ),
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    "*Register a customer channel*\n"
                    "`/relay register #channel Account Name enterprise @owner`"
                ),
            },
        },
        {"type": "actions", "elements": actions},
    ]
    if status.connector_rows:
        blocks.extend(_connector_status_blocks(status.connector_rows))
    return blocks


def _hubspot_connect_url(status: SettingsStatus) -> str:
    """Build the HubSpot OAuth install URL with workspace identity.

    A Slack URL button opens this link in the browser and cannot send an
    Authorization header, so identity travels as query params — same pattern as
    the Slack Search connect button. `/hubspot/install` resolves the workspace
    (and verifies admin) from these before redirecting to HubSpot.
    """
    base = status.app_base_url.rstrip("/") or "https://relay.example.com"
    if not (status.slack_team_id and status.slack_user_id):
        return f"{base}/hubspot/install"
    return (
        f"{base}/hubspot/install"
        f"?team_id={status.slack_team_id}&user_id={status.slack_user_id}"
    )


def _slack_search_connect_url(status: SettingsStatus) -> str:
    base = status.app_base_url.rstrip("/") or "https://relay.example.com"
    if not (status.slack_team_id and status.slack_user_id):
        return f"{base}/slack/search/install"
    return (
        f"{base}/slack/search/install"
        f"?team_id={status.slack_team_id}&user_id={status.slack_user_id}"
    )


def _connector_status_blocks(connector_rows: list[Any]) -> list[dict]:
    blocks: list[dict] = [
        {"type": "section", "text": {"type": "mrkdwn", "text": "*Connected sources*"}},
    ]
    for row in connector_rows:
        display_name = str(row.connector_type).replace("_", " ").title()
        last_synced = row.last_synced_at.isoformat() if row.last_synced_at else "never"
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{display_name}*\nStatus: `{row.sync_status}` · Last synced: `{last_synced}`",
                },
                "accessory": {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Sync"},
                    "action_id": "relay_sync_connector",
                    "value": str(row.id),
                },
            }
        )
    return blocks


async def handle_settings(ack, respond, command) -> None:
    """Handle `/relay settings` with a workspace-scoped setup summary."""
    await ack()

    slack_team_id = command.get("team_id")
    if not slack_team_id:
        await respond(response_type="ephemeral", text="Unable to load settings: missing Slack workspace id.")
        return
    slack_user_id = command.get("user_id", "")

    try:
        async with get_session() as session:
            workspace_result = await session.execute(
                select(Workspace).where(Workspace.slack_team_id == slack_team_id)
            )
            workspace = workspace_result.scalar_one_or_none()

        if workspace is None:
            await respond(response_type="ephemeral", text="RELAY is not installed for this workspace yet.")
            return

        bootstrapped_admin = False
        async with get_session(workspace_id=workspace.id) as session:
            admin_count = await _count(
                session,
                select(func.count())
                .select_from(User)
                .where(
                    User.workspace_id == workspace.id,
                    User.relay_role == "admin",
                    User.deleted_at.is_(None),
                ),
            )
            if admin_count == 0 and slack_user_id:
                await _bootstrap_first_admin(session, workspace.id, slack_user_id)
                admin_count = 1
                bootstrapped_admin = True

            channel_count = await _count(
                session,
                select(func.count())
                .select_from(MonitoredChannel)
                .where(
                    MonitoredChannel.workspace_id == workspace.id,
                    MonitoredChannel.is_active.is_(True),
                ),
            )
            crm_count = await _count(
                session,
                select(func.count())
                .select_from(CrmConnection)
                .where(
                    CrmConnection.workspace_id == workspace.id,
                    CrmConnection.disconnected_at.is_(None),
                ),
            )
            source_count = await _count(
                session,
                select(func.count())
                .select_from(SourceConnector)
                .where(
                    SourceConnector.workspace_id == workspace.id,
                    SourceConnector.disconnected_at.is_(None),
                ),
            )
            connector_result = await session.execute(
                select(SourceConnector)
                .where(
                    SourceConnector.workspace_id == workspace.id,
                    SourceConnector.disconnected_at.is_(None),
                )
                .order_by(SourceConnector.connector_type.asc())
            )
            connector_rows = list(connector_result.scalars())
            search_status = await slack_search_status(
                session,
                workspace_id=workspace.id,
                slack_user_id=slack_user_id,
            )

        status = SettingsStatus(
            installed=True,
            admin_count=admin_count,
            bootstrapped_admin=bootstrapped_admin,
            channel_count=channel_count,
            crm_connected=crm_count > 0,
            source_count=source_count,
            slack_search_connected=search_status.connected,
            app_base_url=get_settings().app_base_url,
            slack_team_id=slack_team_id,
            slack_user_id=slack_user_id,
            connector_rows=connector_rows,
        )
    except Exception as exc:
        logger.exception("settings_failed team=%s", slack_team_id)
        await respond(response_type="ephemeral", text=f"Settings failed: {type(exc).__name__}")
        return

    await respond(response_type="ephemeral", blocks=build_settings_blocks(status))


async def _count(session, statement) -> int:
    result = await session.execute(statement)
    return int(result.scalar_one() or 0)


async def _bootstrap_first_admin(session, workspace_id, slack_user_id: str) -> User:
    result = await session.execute(
        select(User).where(
            User.workspace_id == workspace_id,
            User.slack_user_id == slack_user_id,
        )
    )
    user = result.scalar_one_or_none()
    if user is None:
        user = User(
            workspace_id=workspace_id,
            slack_user_id=slack_user_id,
            relay_role="admin",
        )
        session.add(user)
        await session.flush()
    else:
        user.relay_role = "admin"
        user.deleted_at = None
    return user


def _parse_multiline_csv(value: str) -> list[str]:
    items: list[str] = []
    for raw in value.replace(",", "\n").splitlines():
        item = raw.strip()
        if item:
            items.append(item)
    return items


async def _workspace_for_team(team_id: str) -> Workspace | None:
    async with get_session() as session:
        result = await session.execute(
            select(Workspace).where(Workspace.slack_team_id == team_id)
        )
        return result.scalar_one_or_none()


async def _is_admin(workspace_id: uuid.UUID, slack_user_id: str) -> bool:
    if not slack_user_id:
        return False
    from relay.auth import require_relay_admin

    async with get_session(workspace_id) as session:
        return await require_relay_admin(session, workspace_id, slack_user_id)


async def _upsert_source_connector(
    session,
    *,
    workspace_id: uuid.UUID,
    connector_type: str,
    credentials: str,
    config: dict,
) -> SourceConnector:
    settings = get_settings()
    key = settings.token_encryption_key_bytes
    kms_provider = kms_provider_from_settings(settings)
    if kms_provider is not None:
        workspace_result = await session.execute(select(Workspace).where(Workspace.id == workspace_id))
        workspace = workspace_result.scalar_one()
        key = ensure_workspace_dek(workspace, key, kms_provider)

    encrypted_credentials, nonce = encrypt_token(credentials, key)
    result = await session.execute(
        select(SourceConnector).where(
            SourceConnector.workspace_id == workspace_id,
            SourceConnector.connector_type == connector_type,
            SourceConnector.disconnected_at.is_(None),
        )
    )
    connector = result.scalar_one_or_none()
    if connector is None:
        connector = SourceConnector(
            workspace_id=workspace_id,
            connector_type=connector_type,
            config=config,
            encrypted_credentials=encrypted_credentials,
            encrypted_credentials_nonce=nonce,
            sync_status="not_synced",
        )
        session.add(connector)
        await session.flush()
        return connector

    connector.config = config
    connector.encrypted_credentials = encrypted_credentials
    connector.encrypted_credentials_nonce = nonce
    connector.sync_status = "not_synced"
    connector.last_synced_at = None
    return connector


def _github_modal(team_id: str) -> dict:
    return {
        "type": "modal",
        "callback_id": "relay_save_github_connector",
        "private_metadata": json.dumps({"team_id": team_id}),
        "title": {"type": "plain_text", "text": "Connect GitHub"},
        "submit": {"type": "plain_text", "text": "Save"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "blocks": [
            {
                "type": "input",
                "block_id": "github_token_block",
                "label": {"type": "plain_text", "text": "GitHub token"},
                "element": {"type": "plain_text_input", "action_id": "github_token"},
            },
            {
                "type": "input",
                "block_id": "github_repos_block",
                "label": {"type": "plain_text", "text": "Repositories"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": "github_repos",
                    "multiline": True,
                    "placeholder": {"type": "plain_text", "text": "owner/repo, owner/other-repo"},
                },
            },
            {
                "type": "input",
                "block_id": "github_markdown_paths_block",
                "optional": True,
                "label": {"type": "plain_text", "text": "Markdown paths"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": "github_markdown_paths",
                    "multiline": True,
                    "placeholder": {"type": "plain_text", "text": "README.md, docs/faq.md"},
                },
            },
        ],
    }


def _google_drive_modal(team_id: str) -> dict:
    return {
        "type": "modal",
        "callback_id": "relay_save_google_drive_connector",
        "private_metadata": json.dumps({"team_id": team_id}),
        "title": {"type": "plain_text", "text": "Connect Drive"},
        "submit": {"type": "plain_text", "text": "Save"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "blocks": [
            {
                "type": "input",
                "block_id": "google_folder_block",
                "label": {"type": "plain_text", "text": "Folder ID"},
                "element": {"type": "plain_text_input", "action_id": "google_folder_id"},
            },
            {
                "type": "input",
                "block_id": "google_credentials_block",
                "label": {"type": "plain_text", "text": "Credential JSON"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": "google_credentials_json",
                    "multiline": True,
                },
            },
        ],
    }


async def handle_setup_github_connector(ack, body, client):
    await ack()
    team_id = body.get("team", {}).get("id", "") or body.get("team_id", "")
    user_id = body.get("user", {}).get("id", "")
    trigger_id = body.get("trigger_id", "")
    workspace = await _workspace_for_team(team_id)
    if workspace is None or not trigger_id or not await _is_admin(workspace.id, user_id):
        return
    await client.views_open(trigger_id=trigger_id, view=_github_modal(team_id))


async def handle_setup_google_drive_connector(ack, body, client):
    await ack()
    team_id = body.get("team", {}).get("id", "") or body.get("team_id", "")
    user_id = body.get("user", {}).get("id", "")
    trigger_id = body.get("trigger_id", "")
    workspace = await _workspace_for_team(team_id)
    if workspace is None or not trigger_id or not await _is_admin(workspace.id, user_id):
        return
    await client.views_open(trigger_id=trigger_id, view=_google_drive_modal(team_id))


async def handle_sync_connector(ack, body, respond):
    await ack()
    actions = body.get("actions", [])
    connector_id_str = actions[0].get("value", "") if actions else ""
    team_id = body.get("team", {}).get("id", "") or body.get("team_id", "")
    user_id = body.get("user", {}).get("id", "")
    try:
        connector_id = uuid.UUID(connector_id_str)
    except ValueError:
        return
    workspace = await _workspace_for_team(team_id)
    if workspace is None or not await _is_admin(workspace.id, user_id):
        return

    from relay.worker.connector_tasks import sync_connector

    sync_connector.delay(str(workspace.id), str(connector_id))
    await respond(response_type="ephemeral", text="Source sync started.")


async def handle_sync_hubspot(ack, body, respond):
    await ack()
    team_id = body.get("team", {}).get("id", "") or body.get("team_id", "")
    user_id = body.get("user", {}).get("id", "")
    workspace = await _workspace_for_team(team_id)
    if workspace is None or not await _is_admin(workspace.id, user_id):
        return

    from relay.worker.hubspot_tasks import sync_hubspot_accounts

    sync_hubspot_accounts.delay(str(workspace.id))
    await respond(response_type="ephemeral", text="HubSpot sync started.")


async def handle_save_github_connector(ack, body):
    metadata = json.loads(body.get("view", {}).get("private_metadata", "{}"))
    team_id = metadata.get("team_id", "")
    user_id = body.get("user", {}).get("id", "")
    workspace = await _workspace_for_team(team_id)
    if workspace is None or not await _is_admin(workspace.id, user_id):
        await ack()
        return

    values = body.get("view", {}).get("state", {}).get("values", {})
    token = values.get("github_token_block", {}).get("github_token", {}).get("value", "")
    repos_raw = values.get("github_repos_block", {}).get("github_repos", {}).get("value", "")
    markdown_raw = (
        values.get("github_markdown_paths_block", {})
        .get("github_markdown_paths", {})
        .get("value", "")
    )
    repos = _parse_multiline_csv(repos_raw)
    markdown_paths = _parse_multiline_csv(markdown_raw or "")
    errors = {}
    if not token.strip():
        errors["github_token_block"] = "Enter a GitHub token."
    if not repos:
        errors["github_repos_block"] = "Enter at least one repository as owner/repo."
    if errors:
        await ack(response_action="errors", errors=errors)
        return

    await ack()
    async with get_session(workspace.id) as session:
        connector = await _upsert_source_connector(
            session,
            workspace_id=workspace.id,
            connector_type="github",
            credentials=token.strip(),
            config={"repo_list": repos, "markdown_paths": markdown_paths},
        )
        connector_id = connector.id

    from relay.worker.connector_tasks import sync_connector

    sync_connector.delay(str(workspace.id), str(connector_id))


async def handle_disconnect_slack_search(ack, body, respond) -> None:
    """Revoke the requesting user's Slack search token."""
    await ack()
    slack_team_id = (body.get("team") or {}).get("id") or body.get("team_id", "")
    slack_user_id = (body.get("user") or {}).get("id") or body.get("user_id", "")
    if not slack_team_id or not slack_user_id:
        await respond(response_type="ephemeral", text="Unable to disconnect: missing workspace or user.")
        return
    try:
        async with get_session() as session:
            workspace_result = await session.execute(
                select(Workspace).where(Workspace.slack_team_id == slack_team_id)
            )
            workspace = workspace_result.scalar_one_or_none()
        if workspace is None:
            await respond(response_type="ephemeral", text="Workspace not found.")
            return
        async with get_session(workspace_id=workspace.id) as session:
            await revoke_user_search_tokens(session, workspace_id=workspace.id, slack_user_id=slack_user_id)
    except Exception:
        logger.exception("disconnect_slack_search_failed team=%s user=%s", slack_team_id, slack_user_id)
        await respond(response_type="ephemeral", text="Failed to disconnect Slack Search. Please try again.")
        return
    await respond(response_type="ephemeral", text=":white_check_mark: Slack Search context disconnected.")


async def handle_save_google_drive_connector(ack, body):
    metadata = json.loads(body.get("view", {}).get("private_metadata", "{}"))
    team_id = metadata.get("team_id", "")
    user_id = body.get("user", {}).get("id", "")
    workspace = await _workspace_for_team(team_id)
    if workspace is None or not await _is_admin(workspace.id, user_id):
        await ack()
        return

    values = body.get("view", {}).get("state", {}).get("values", {})
    folder_id = values.get("google_folder_block", {}).get("google_folder_id", {}).get("value", "")
    credentials_json = (
        values.get("google_credentials_block", {})
        .get("google_credentials_json", {})
        .get("value", "")
    )
    errors = {}
    if not folder_id.strip():
        errors["google_folder_block"] = "Enter a Google Drive folder ID."
    try:
        json.loads(credentials_json or "")
    except json.JSONDecodeError:
        errors["google_credentials_block"] = "Enter valid credential JSON."
    if errors:
        await ack(response_action="errors", errors=errors)
        return

    await ack()
    async with get_session(workspace.id) as session:
        await _upsert_source_connector(
            session,
            workspace_id=workspace.id,
            connector_type="google_drive",
            credentials=credentials_json,
            config={"folder_id": folder_id.strip()},
        )
