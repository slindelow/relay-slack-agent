from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from relay.context import mcp_server


@pytest.mark.asyncio
async def test_mcp_tool_rejects_invalid_workspace_id():
    with pytest.raises(ValueError):
        await mcp_server.get_question_context_tool("not-a-uuid", "also-not-a-uuid")


@pytest.mark.asyncio
async def test_mcp_search_tool_returns_serialized_sources():
    payload = {
        "title": "SSO runbook",
        "provider": "google_drive",
        "url": "https://docs.example.com/sso",
        "excerpt": "Rotate the certificate.",
        "visibility": "customer_safe",
    }
    source = SimpleNamespace(to_prompt_dict=lambda: payload)

    class SessionContext:
        async def __aenter__(self):
            return AsyncMock()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    with (
        patch("relay.context.mcp_server.get_session", return_value=SessionContext()),
        patch("relay.context.mcp_server.search_indexed_knowledge", new=AsyncMock(return_value=[source])),
    ):
        results = await mcp_server.search_indexed_knowledge_tool(
            "00000000-0000-0000-0000-000000000001",
            "How do we rotate SSO?",
            top_k=1,
        )

    assert results == [payload]
