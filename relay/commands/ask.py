"""Handler logic for the /relay ask subcommand."""

from __future__ import annotations

import logging
import re

from sqlalchemy import select

from relay.context.contracts import ContextSource
from relay.context.service import search_indexed_knowledge, search_slack_context
from relay.context.slack_rts import slack_search_status
from relay.db.models import Workspace
from relay.db.session import get_session

logger = logging.getLogger(__name__)

# Matches "ask" followed by one-or-more spaces (with optional trailing content),
# OR a bare "ask" at end-of-string — both require a word boundary so "asking" is not touched.
_ASK_PREFIX_RE = re.compile(r"^ask(?:\s+|$)", re.IGNORECASE)


def _parse_ask_query(text: str) -> str:
    # Apply prefix regex before stripping so trailing-space-only input ("ask ") works correctly.
    return _ASK_PREFIX_RE.sub("", text.lstrip()).strip()


def _truncate(text: str, max_chars: int = 150) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "..."


def _escape_mrkdwn(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _format_result_blocks(chunks: list[ContextSource], *, slack_search_connected: bool = True) -> list[dict]:
    blocks: list[dict] = [
        {"type": "section", "text": {"type": "mrkdwn", "text": "*Top RELAY sources*"}},
        {"type": "divider"},
    ]

    for chunk in chunks:
        title = chunk.title or "Retrieved source"
        provider = chunk.provider or "retrieval"
        url = chunk.url
        escaped_title = _escape_mrkdwn(title)
        if url and url.startswith("https://"):
            title_text = f"<{url}|{escaped_title}>"
        else:
            title_text = escaped_title
        freshness = "stale" if chunk.stale else "fresh"
        visibility = "internal" if chunk.visibility == "internal" else "customer-safe"
        excerpt = _escape_mrkdwn(_truncate(chunk.excerpt.replace("\n", " ")))

        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{title_text}* `{provider}` `{visibility}` _{freshness}_\n>{excerpt}",
                },
            }
        )
    if not slack_search_connected:
        blocks.append(
            {
                "type": "context",
                "elements": [{
                    "type": "mrkdwn",
                    "text": "Connect Slack Search in `/relay settings` to include internal Slack context.",
                }],
            }
        )

    return blocks


async def handle_ask(ack, respond, command) -> None:
    """Handle `/relay ask <question>` without creating workflow records."""
    await ack()

    query = _parse_ask_query(command.get("text") or "")
    if not query:
        await respond(response_type="ephemeral", text="Usage: /relay ask <your question>")
        return

    slack_team_id = command.get("team_id")
    if not slack_team_id:
        await respond(response_type="ephemeral", text="Unable to ask: missing Slack workspace id.")
        return

    try:
        async with get_session() as session:
            workspace_result = await session.execute(
                select(Workspace).where(Workspace.slack_team_id == slack_team_id)
            )
            workspace = workspace_result.scalar_one_or_none()
            if workspace is None:
                await respond(response_type="ephemeral", text="RELAY is not installed for this workspace yet.")
                return

        async with get_session(workspace_id=workspace.id) as session:
            status = await slack_search_status(
                session,
                workspace_id=workspace.id,
                slack_user_id=command.get("user_id", ""),
            )
            indexed_chunks = await search_indexed_knowledge(
                workspace.id,
                query,
                session,
                top_k=5,
                actor_slack_user_id=command.get("user_id", ""),
            )
            slack_chunks = await search_slack_context(
                workspace.id,
                command.get("user_id", ""),
                query,
                session,
                top_k=5,
            )
            chunks = [*indexed_chunks, *slack_chunks]
            slack_search_connected = status.connected
    except Exception as exc:
        logger.exception("ask_failed team=%s", slack_team_id)
        await respond(response_type="ephemeral", text=f"Ask failed: {type(exc).__name__}")
        return

    if not chunks:
        text = "No relevant sources found in connected knowledge base."
        if not slack_search_connected:
            text += " Connect Slack Search in `/relay settings` to include internal Slack context."
        await respond(response_type="ephemeral", text=text)
        return

    await respond(
        response_type="ephemeral",
        blocks=_format_result_blocks(chunks, slack_search_connected=slack_search_connected),
    )
