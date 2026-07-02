"""Unit tests for the GitHub connector."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from relay.connectors.github import GitHubConnector, _is_stale


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_connector_row(connector_id: uuid.UUID, workspace_id: uuid.UUID):
    from relay.crypto import encrypt_token
    key = bytes.fromhex("a" * 64)
    ciphertext, nonce = encrypt_token("ghp_token", key)
    row = MagicMock()
    row.id = connector_id
    row.workspace_id = workspace_id
    row.connector_type = "github"
    row.config = {"repo_list": ["owner/repo"], "markdown_paths": ["CHANGELOG.md"]}
    row.encrypted_credentials = ciphertext
    row.encrypted_credentials_nonce = nonce
    row.disconnected_at = None
    row.last_synced_at = None
    row.sync_status = "not_synced"
    return row, key


def _mock_issue(number: int, title: str, body: str = "") -> MagicMock:
    issue = MagicMock()
    issue.number = number
    issue.title = title
    issue.body = body
    issue.state = "open"
    issue.labels = []
    issue.html_url = f"https://github.com/owner/repo/issues/{number}"
    issue.updated_at = datetime(2024, 1, 1, tzinfo=UTC)
    issue.pull_request = None
    return issue


def _mock_pr(number: int, title: str) -> MagicMock:
    pr = MagicMock()
    pr.number = number
    pr.title = title
    pr.body = "PR body"
    pr.state = "open"
    pr.labels = []
    pr.html_url = f"https://github.com/owner/repo/pull/{number}"
    pr.updated_at = datetime(2024, 1, 1, tzinfo=UTC)
    return pr


def _mock_release(release_id: int, tag: str) -> MagicMock:
    rel = MagicMock()
    rel.id = release_id
    rel.tag_name = tag
    rel.title = f"Release {tag}"
    rel.body = "Release notes"
    rel.html_url = f"https://github.com/owner/repo/releases/tag/{tag}"
    rel.published_at = datetime(2024, 1, 1, tzinfo=UTC)
    return rel


def _mock_tree_element(path: str, type_: str) -> MagicMock:
    el = MagicMock()
    el.path = path
    el.type = type_  # "tree" for directories, "blob" for files
    return el


def _empty_tree() -> MagicMock:
    """A git tree with no entries — yields no structure document."""
    return MagicMock(tree=[])


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_creates_rows_for_issues_prs_releases():
    workspace_id = uuid.uuid4()
    connector_id = uuid.uuid4()
    connector_row, key = _make_connector_row(connector_id, workspace_id)

    issue = _mock_issue(1, "Bug report")
    pr = _mock_pr(2, "Fix something")
    release = _mock_release(100, "v1.0.0")

    repo = MagicMock()
    repo.get_issues.return_value = [issue][:200]
    repo.get_pulls.return_value = [pr][:200]
    repo.get_releases.return_value = [release][:50]
    repo.get_git_tree.return_value = _empty_tree()

    md_file = MagicMock()
    md_file.decoded_content = b"# Changelog\nSome content"
    md_file.html_url = "https://github.com/owner/repo/blob/main/CHANGELOG.md"
    repo.get_contents.return_value = md_file

    gh_client = MagicMock()
    gh_client.get_repo.return_value = repo

    session = AsyncMock()
    session.add = MagicMock()
    connector_result = MagicMock()
    connector_result.scalar_one_or_none.return_value = connector_row

    # For each item, return None (new doc)
    no_doc = MagicMock()
    no_doc.scalar_one_or_none.return_value = None

    session.execute = AsyncMock(side_effect=[connector_result, no_doc, no_doc, no_doc, no_doc])
    session.flush = AsyncMock()

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("relay.connectors.github.get_session", return_value=ctx),
        patch("relay.connectors.github.get_settings") as mock_settings,
        patch("relay.connectors.github.Github", return_value=gh_client),
        patch("relay.connectors.github.embed_chunks", new=AsyncMock(return_value=[])),
    ):
        mock_settings.return_value.token_encryption_key_bytes = key
        mock_settings.return_value.github_token = ""
        await GitHubConnector().sync(workspace_id, connector_id)

    assert session.add.call_count == 4  # issue + pr + release + markdown
    assert session.flush.call_count == 4


@pytest.mark.asyncio
async def test_sync_indexes_repository_structure():
    """The connector synthesizes a document describing the repo's folder layout so
    that "what's the folder structure" questions have something to retrieve."""
    workspace_id = uuid.uuid4()
    connector_id = uuid.uuid4()
    connector_row, key = _make_connector_row(connector_id, workspace_id)
    connector_row.config = {"repo_list": ["owner/repo"], "markdown_paths": []}

    repo = MagicMock()
    repo.get_issues.return_value = []
    repo.get_pulls.return_value = []
    repo.get_releases.return_value = []
    repo.html_url = "https://github.com/owner/repo"
    repo.default_branch = "main"
    repo.get_git_tree.return_value = MagicMock(
        tree=[
            _mock_tree_element("relay", "tree"),
            _mock_tree_element("relay/connectors", "tree"),
            _mock_tree_element("docs", "tree"),
            _mock_tree_element("docs/deployment", "tree"),
            _mock_tree_element("README.md", "blob"),
            _mock_tree_element("relay/connectors/github.py", "blob"),
        ]
    )

    gh_client = MagicMock()
    gh_client.get_repo.return_value = repo

    session = AsyncMock()
    session.add = MagicMock()
    connector_result = MagicMock()
    connector_result.scalar_one_or_none.return_value = connector_row
    no_doc = MagicMock()
    no_doc.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(side_effect=[connector_result, no_doc])
    session.flush = AsyncMock()

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("relay.connectors.github.get_session", return_value=ctx),
        patch("relay.connectors.github.get_settings") as mock_settings,
        patch("relay.connectors.github.Github", return_value=gh_client),
        patch("relay.connectors.github.embed_chunks", new=AsyncMock(return_value=[])) as mock_embed,
    ):
        mock_settings.return_value.token_encryption_key_bytes = key
        mock_settings.return_value.github_token = ""
        await GitHubConnector().sync(workspace_id, connector_id)

    # Exactly one document indexed: the structure manifest.
    assert session.add.call_count == 1
    embedded_chunks = mock_embed.await_args.kwargs["chunks"]
    embedded_text = "\n".join(embedded_chunks)
    assert "relay" in embedded_text
    assert "docs" in embedded_text
    assert "docs/deployment" in embedded_text
    assert "Human-readable layout summary" in embedded_text
    assert "relay/: application code" in embedded_text


@pytest.mark.asyncio
async def test_sync_skips_unchanged_hash():
    workspace_id = uuid.uuid4()
    connector_id = uuid.uuid4()
    connector_row, key = _make_connector_row(connector_id, workspace_id)

    issue = _mock_issue(1, "Unchanged issue", "Body")
    text = "ISSUE\nUnchanged issue\n\nBody"
    existing_hash = hashlib.sha256(text.encode()).hexdigest()

    repo = MagicMock()
    repo.get_issues.return_value = [issue]
    repo.get_pulls.return_value = []
    repo.get_releases.return_value = []
    repo.get_git_tree.return_value = _empty_tree()
    repo.get_contents.side_effect = Exception("not found")

    gh_client = MagicMock()
    gh_client.get_repo.return_value = repo

    existing_doc = MagicMock()
    existing_doc.content_hash = existing_hash

    session = AsyncMock()
    session.add = MagicMock()
    connector_result = MagicMock()
    connector_result.scalar_one_or_none.return_value = connector_row
    doc_result = MagicMock()
    doc_result.scalar_one_or_none.return_value = existing_doc
    session.execute = AsyncMock(side_effect=[connector_result, doc_result])
    session.flush = AsyncMock()

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("relay.connectors.github.get_session", return_value=ctx),
        patch("relay.connectors.github.get_settings") as mock_settings,
        patch("relay.connectors.github.Github", return_value=gh_client),
        patch("relay.connectors.github.embed_chunks", new=AsyncMock()) as mock_embed,
    ):
        mock_settings.return_value.token_encryption_key_bytes = key
        mock_settings.return_value.github_token = ""
        await GitHubConnector().sync(workspace_id, connector_id)

    mock_embed.assert_not_called()


def test_citation_stale_flag():
    connector = GitHubConnector()

    doc_fresh = MagicMock()
    doc_fresh.title = "Fresh doc"
    doc_fresh.url = "https://github.com/o/r/issues/1"
    doc_fresh.last_synced_at = datetime.now(UTC) - timedelta(hours=10)
    doc_fresh.config = {"status": "open", "labels": [], "updated_at": None}

    chunk_fresh = MagicMock()
    chunk_fresh._doc = doc_fresh
    citation = connector.citation(chunk_fresh)
    assert citation["stale"] is False

    doc_stale = MagicMock()
    doc_stale.title = "Stale doc"
    doc_stale.url = "https://github.com/o/r/issues/2"
    doc_stale.last_synced_at = datetime.now(UTC) - timedelta(hours=72)
    doc_stale.config = {"status": "closed", "labels": [], "updated_at": None}

    chunk_stale = MagicMock()
    chunk_stale._doc = doc_stale
    citation_stale = connector.citation(chunk_stale)
    assert citation_stale["stale"] is True


def test_is_stale_none():
    assert _is_stale(None) is True


def test_is_stale_recent():
    assert _is_stale(datetime.now(UTC) - timedelta(hours=1)) is False


def test_is_stale_old():
    assert _is_stale(datetime.now(UTC) - timedelta(hours=100)) is True
