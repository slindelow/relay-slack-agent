"""Handler logic for the /relay ask subcommand."""

from __future__ import annotations

import logging
import re

from sqlalchemy import select

from relay.context.answers import (
    dedupe_and_rank_sources,
    escape_mrkdwn,
    extractive_answer,
    is_customer_concern_query,
    is_repo_structure_query,
    provider_label,
)
from relay.context.contracts import ContextSource
from relay.context.service import search_customer_history, search_indexed_knowledge, search_slack_context
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


_escape_mrkdwn = escape_mrkdwn
_is_repo_structure_query = is_repo_structure_query
_is_customer_concern_query = is_customer_concern_query
_dedupe_and_rank_sources = dedupe_and_rank_sources
_extractive_answer = extractive_answer
_provider_label = provider_label


def _citation_line(index: int, chunk: ContextSource) -> str:
    title = _escape_mrkdwn(chunk.title or "Retrieved source")
    if chunk.url and chunk.url.startswith("https://"):
        title_text = f"<{chunk.url}|{title}>"
    else:
        title_text = title
    return f"{index}. {title_text} ({_provider_label(chunk.provider)})"


def _format_result_blocks(
    query: str,
    chunks: list[ContextSource],
    *,
    slack_search_connected: bool = True,
) -> list[dict]:
    ranked_chunks = _dedupe_and_rank_sources(query, chunks)
    if not ranked_chunks:
        return []
    answer = _escape_mrkdwn(_extractive_answer(query, ranked_chunks))
    citation_lines = [_citation_line(index, chunk) for index, chunk in enumerate(ranked_chunks[:3], start=1)]

    blocks: list[dict] = [
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*Answer*\n{answer}"}},
        {"type": "divider"},
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*Citations*\n" + "\n".join(citation_lines)},
        },
    ]
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
        await respond(
            response_type="ephemeral",
            text=(
                "*Ask RELAY knowledge*\n"
                "Use `/relay ask <your question>`.\n"
                "Example: `/relay ask where do we handle Slack event ingestion?`"
            ),
        )
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
                top_k=8 if _is_repo_structure_query(query) else 5,
                actor_slack_user_id=command.get("user_id", ""),
            )
            slack_chunks = await search_slack_context(
                workspace.id,
                command.get("user_id", ""),
                query,
                session,
                top_k=5,
            )
            customer_history_chunks = []
            if _is_customer_concern_query(query):
                customer_history_chunks = await search_customer_history(
                    workspace.id,
                    query,
                    session,
                    top_k=10,
                    actor_slack_user_id=command.get("user_id", ""),
                )
            chunks = _dedupe_and_rank_sources(query, [*customer_history_chunks, *indexed_chunks, *slack_chunks])
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
        blocks=_format_result_blocks(query, chunks, slack_search_connected=slack_search_connected),
    )
