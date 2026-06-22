"""MCP facade for RELAY's governed context tools."""

from __future__ import annotations

import uuid
from typing import Any

from relay.context.service import (
    assemble_evidence_for_question,
    get_account_context,
    get_question_context,
    search_indexed_knowledge,
    search_slack_context,
)
from relay.db.session import get_session


async def get_question_context_tool(workspace_id: str, question_id: str) -> dict[str, Any]:
    wid = uuid.UUID(workspace_id)
    qid = uuid.UUID(question_id)
    async with get_session(wid) as session:
        context = await get_question_context(wid, qid, session)
        return context.to_prompt_dict()


async def get_account_context_tool(workspace_id: str, account_id: str) -> dict[str, Any]:
    wid = uuid.UUID(workspace_id)
    aid = uuid.UUID(account_id)
    async with get_session(wid) as session:
        context = await get_account_context(wid, aid, session)
        return context.to_prompt_dict()


async def search_indexed_knowledge_tool(
    workspace_id: str,
    query: str,
    top_k: int = 5,
) -> list[dict[str, Any]]:
    wid = uuid.UUID(workspace_id)
    async with get_session(wid) as session:
        sources = await search_indexed_knowledge(wid, query, session, top_k=top_k)
        return [source.to_prompt_dict() for source in sources]


async def search_slack_context_tool(
    workspace_id: str,
    acting_slack_user_id: str,
    query: str,
    top_k: int = 5,
    channel_filter: list[str] | None = None,
) -> list[dict[str, Any]]:
    wid = uuid.UUID(workspace_id)
    async with get_session(wid) as session:
        sources = await search_slack_context(
            wid,
            acting_slack_user_id,
            query,
            session,
            top_k=top_k,
            channel_filter=channel_filter,
        )
        return [source.to_prompt_dict() for source in sources]


async def assemble_evidence_for_question_tool(
    workspace_id: str,
    question_id: str,
    acting_slack_user_id: str | None = None,
) -> dict[str, Any]:
    wid = uuid.UUID(workspace_id)
    qid = uuid.UUID(question_id)
    async with get_session(wid) as session:
        bundle = await assemble_evidence_for_question(
            wid,
            qid,
            session,
            acting_slack_user_id=acting_slack_user_id,
        )
        return bundle.to_prompt_dict()


def build_mcp_server():
    """Return a FastMCP server when the optional MCP runtime is installed."""
    try:
        from mcp.server.fastmcp import FastMCP
    except Exception as exc:  # pragma: no cover - exercised only without optional dep
        raise RuntimeError("Install the `mcp` package to run the RELAY MCP server") from exc

    server = FastMCP("relay-context")
    server.tool(name="get_question_context")(get_question_context_tool)
    server.tool(name="get_account_context")(get_account_context_tool)
    server.tool(name="search_indexed_knowledge")(search_indexed_knowledge_tool)
    server.tool(name="search_slack_context")(search_slack_context_tool)
    server.tool(name="assemble_evidence_for_question")(assemble_evidence_for_question_tool)
    return server


if __name__ == "__main__":
    build_mcp_server().run()
