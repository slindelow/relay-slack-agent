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


# Alias required by MCP spec: question_lookup
question_lookup_tool = get_question_context_tool


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


# Alias required by MCP spec: evidence_assembly
evidence_assembly_tool = assemble_evidence_for_question_tool


async def draft_generation_tool(
    workspace_id: str,
    question_id: str,
    acting_slack_user_id: str | None = None,
) -> dict[str, Any]:
    """Assemble evidence and generate a draft — the load-bearing MCP entrypoint for draft generation."""
    from relay.drafting.generator import generate_draft

    wid = uuid.UUID(workspace_id)
    qid = uuid.UUID(question_id)
    async with get_session(wid) as session:
        bundle = await assemble_evidence_for_question(
            wid,
            qid,
            session,
            acting_slack_user_id=acting_slack_user_id,
        )
        output = await generate_draft(wid, qid, bundle, session)

    return {
        "question_id": question_id,
        "workspace_id": workspace_id,
        "customer_draft": output.customer_draft,
        "internal_brief": output.internal_brief,
        "confidence": output.confidence,
        "risks_or_unknowns": output.risks_or_unknowns,
        "recommended_next_action": output.recommended_next_action,
        "requires_human_review": True,
        "source_count": len(bundle.sources),
    }


def build_mcp_server():
    """Return a FastMCP server when the optional MCP runtime is installed."""
    try:
        from mcp.server.fastmcp import FastMCP
        from mcp.server.transport_security import TransportSecuritySettings
    except Exception as exc:  # pragma: no cover - exercised only without optional dep
        raise RuntimeError("Install the `mcp` package to run the RELAY MCP server") from exc

    # Allow the app's own hostname (from APP_BASE_URL) plus standard localhost variants.
    # FastMCP 1.28+ auto-enables DNS rebinding protection when host="127.0.0.1",
    # which would reject all non-localhost clients unless we configure allowed_hosts.
    from urllib.parse import urlparse

    from relay.config import get_settings

    _settings = get_settings()
    _app_host = urlparse(_settings.app_base_url).netloc  # e.g. "web-production-acd3.up.railway.app"
    _allowed_hosts = list(
        {
            _app_host,
            "localhost",
            "localhost:*",
            "127.0.0.1",
            "127.0.0.1:*",
            "testserver",  # Starlette TestClient default host used in tests
        }
    )
    transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=_allowed_hosts,
    )

    server = FastMCP("relay-context", transport_security=transport_security)

    # Primary tools (original names)
    server.tool(name="get_question_context")(get_question_context_tool)
    server.tool(name="get_account_context")(get_account_context_tool)
    server.tool(name="search_indexed_knowledge")(search_indexed_knowledge_tool)
    server.tool(name="search_slack_context")(search_slack_context_tool)
    server.tool(name="assemble_evidence_for_question")(assemble_evidence_for_question_tool)

    # Required MCP spec tool names
    server.tool(name="question_lookup")(question_lookup_tool)
    server.tool(name="evidence_assembly")(evidence_assembly_tool)
    server.tool(name="draft_generation")(draft_generation_tool)

    return server


if __name__ == "__main__":
    build_mcp_server().run()
