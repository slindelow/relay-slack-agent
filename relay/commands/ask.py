"""Handler logic for the /relay ask subcommand."""

from __future__ import annotations

import logging

from sqlalchemy import select

from relay.connectors.retrieval import RetrievedChunk, retrieve
from relay.db.models import Workspace
from relay.db.session import get_session

logger = logging.getLogger(__name__)


def _parse_ask_query(text: str) -> str:
    stripped = text.strip()
    if stripped.lower().startswith("ask"):
        stripped = stripped[len("ask"):].strip()
    return stripped


def _truncate(text: str, max_chars: int = 150) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "..."


def _format_result_blocks(chunks: list[RetrievedChunk]) -> list[dict]:
    blocks: list[dict] = [
        {"type": "section", "text": {"type": "mrkdwn", "text": "*Top RELAY sources*"}},
        {"type": "divider"},
    ]

    for chunk in chunks:
        citation = chunk.citation or {}
        title = citation.get("title") or "Retrieved source"
        provider = citation.get("provider") or "retrieval"
        url = citation.get("url")
        title_text = f"<{url}|{title}>" if url else title
        freshness = "stale" if citation.get("stale") else "fresh"
        excerpt = _truncate(chunk.content.replace("\n", " "))

        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{title_text}* `{provider}` _{freshness}_\n>{excerpt}",
                },
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
            chunks = await retrieve(workspace.id, query, session, top_k=5)
    except Exception as exc:
        logger.exception("ask_failed team=%s", slack_team_id)
        await respond(response_type="ephemeral", text=f"Ask failed: {type(exc).__name__}")
        return

    if not chunks:
        await respond(
            response_type="ephemeral",
            text="No relevant sources found in connected knowledge base.",
        )
        return

    await respond(response_type="ephemeral", blocks=_format_result_blocks(chunks))
