"""GitHub source connector for issues, PRs, releases, and selected markdown."""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from relay.config import get_settings
from relay.connectors.base import Connector
from relay.connectors.chunking import chunk_text
from relay.connectors.embeddings import embed_chunks
from relay.crypto import decrypt_token, kms_provider_from_settings, workspace_encryption_key
from relay.db.models import KnowledgeChunk, SourceConnector, SourceDocument, Workspace
from relay.db.session import get_session

try:
    from github import Github
except ModuleNotFoundError:  # pragma: no cover - exercised when dependency is absent
    Github = None

_STALE_AFTER = timedelta(hours=48)


@dataclass(frozen=True)
class _SourceItem:
    external_id: str
    title: str
    url: str
    content: str
    provider_updated_at: datetime | None
    config: dict


def _is_stale(last_synced_at: datetime | None) -> bool:
    if last_synced_at is None:
        return True
    if last_synced_at.tzinfo is None:
        last_synced_at = last_synced_at.replace(tzinfo=UTC)
    return datetime.now(UTC) - last_synced_at > _STALE_AFTER


def _labels(item) -> list[str]:
    return [getattr(label, "name", str(label)) for label in (getattr(item, "labels", []) or [])]


def _item_config(item_type: str, item, updated_at: datetime | None) -> dict:
    return {
        "type": item_type,
        "status": getattr(item, "state", None),
        "labels": _labels(item),
        "url": getattr(item, "html_url", None),
        "updated_at": updated_at.isoformat() if updated_at else None,
    }


def _structure_item(repo, repo_name: str) -> _SourceItem | None:
    """Synthesize a document describing the repo's directory layout.

    Folder/architecture questions ("what's the folder setup?") have no issue, PR,
    or release to match against, so without this the knowledge base has nothing to
    retrieve and the draft falls back to a low-confidence holding reply. We index
    the repository tree itself as a first-class document so those questions land.
    """
    try:
        tree = repo.get_git_tree(repo.default_branch, recursive=True)
        elements = list(getattr(tree, "tree", []) or [])
    except Exception:
        return None

    dirs: list[str] = []
    files: list[str] = []
    for element in elements:
        path = getattr(element, "path", None)
        if not path:
            continue
        if getattr(element, "type", None) == "tree":
            dirs.append(path)
        else:
            files.append(path)

    if not dirs and not files:
        return None

    dirs.sort()
    top_level = sorted({path.split("/")[0] for path in dirs + files})
    repo_url = getattr(repo, "html_url", None) or f"https://github.com/{repo_name}"

    lines = [
        f"REPOSITORY STRUCTURE for {repo_name}",
        "",
        "This document describes the folder and file layout of the repository.",
        "",
        "Top-level entries:",
        *[f"- {name}" for name in top_level],
    ]
    if dirs:
        lines += ["", "All directories:", *[f"- {d}/" for d in dirs]]

    return _SourceItem(
        external_id=f"{repo_name}:structure",
        title=f"{repo_name} repository structure",
        url=repo_url,
        content="\n".join(lines),
        provider_updated_at=None,
        config={
            "type": "structure",
            "status": None,
            "labels": [],
            "url": repo_url,
            "updated_at": None,
        },
    )


def _github_items(repo, repo_name: str, markdown_paths: Iterable[str]) -> list[_SourceItem]:
    items: list[_SourceItem] = []

    structure = _structure_item(repo, repo_name)
    if structure is not None:
        items.append(structure)

    for issue in list(repo.get_issues(state="all"))[:200]:
        if getattr(issue, "pull_request", None):
            continue
        updated_at = getattr(issue, "updated_at", None)
        content = f"ISSUE\n{issue.title}\n\n{getattr(issue, 'body', '') or ''}"
        items.append(
            _SourceItem(
                external_id=f"{repo_name}:issue:{issue.number}",
                title=issue.title,
                url=issue.html_url,
                content=content,
                provider_updated_at=updated_at,
                config=_item_config("issue", issue, updated_at),
            )
        )

    for pr in list(repo.get_pulls(state="all"))[:200]:
        updated_at = getattr(pr, "updated_at", None)
        content = f"PR\n{pr.title}\n\n{getattr(pr, 'body', '') or ''}"
        items.append(
            _SourceItem(
                external_id=f"{repo_name}:pr:{pr.number}",
                title=pr.title,
                url=pr.html_url,
                content=content,
                provider_updated_at=updated_at,
                config=_item_config("pr", pr, updated_at),
            )
        )

    for release in list(repo.get_releases())[:50]:
        updated_at = getattr(release, "published_at", None)
        title = getattr(release, "title", None) or getattr(release, "tag_name", "")
        content = f"RELEASE\n{title}\n\n{getattr(release, 'body', '') or ''}"
        items.append(
            _SourceItem(
                external_id=f"{repo_name}:release:{release.id}",
                title=title,
                url=release.html_url,
                content=content,
                provider_updated_at=updated_at,
                config={
                    "type": "release",
                    "status": None,
                    "labels": [],
                    "url": release.html_url,
                    "updated_at": updated_at.isoformat() if updated_at else None,
                },
            )
        )

    for path in markdown_paths:
        try:
            file_obj = repo.get_contents(path)
        except Exception:
            continue
        content = file_obj.decoded_content.decode("utf-8", errors="replace")
        items.append(
            _SourceItem(
                external_id=f"{repo_name}:markdown:{path}",
                title=path,
                url=getattr(file_obj, "html_url", ""),
                content=content,
                provider_updated_at=None,
                config={
                    "type": "markdown",
                    "status": None,
                    "labels": [],
                    "url": getattr(file_obj, "html_url", None),
                    "updated_at": None,
                },
            )
        )

    return items


class GitHubConnector(Connector):
    """Sync selected GitHub repo data into RELAY knowledge chunks."""

    async def sync(self, workspace_id: uuid.UUID, connector_id: uuid.UUID) -> None:
        if Github is None:
            raise RuntimeError("PyGitHub is required for GitHub sync")

        settings = get_settings()
        async with get_session(workspace_id) as session:
            result = await session.execute(
                select(SourceConnector).where(
                    SourceConnector.workspace_id == workspace_id,
                    SourceConnector.id == connector_id,
                    SourceConnector.connector_type == "github",
                    SourceConnector.disconnected_at.is_(None),
                )
            )
            connector = result.scalar_one_or_none()
            if connector is None:
                return

            key = settings.token_encryption_key_bytes
            kms_provider = kms_provider_from_settings(settings)
            if kms_provider is not None:
                workspace_result = await session.execute(select(Workspace).where(Workspace.id == workspace_id))
                workspace = workspace_result.scalar_one()
                key = workspace_encryption_key(workspace, key, kms_provider)

            token = settings.github_token
            if connector.encrypted_credentials:
                token = decrypt_token(
                    connector.encrypted_credentials,
                    connector.encrypted_credentials_nonce,
                    key,
                )
            if not token:
                return

            client = Github(token)
            repo_names = connector.config.get("repo_list") or []
            markdown_paths = connector.config.get("markdown_paths") or []

            for repo_name in repo_names:
                repo = client.get_repo(repo_name)
                for item in _github_items(repo, repo_name, markdown_paths):
                    await self._sync_item(session, workspace_id, connector.id, item)

    async def _sync_item(
        self,
        session,
        workspace_id: uuid.UUID,
        connector_id: uuid.UUID,
        item: _SourceItem,
    ) -> None:
        content_hash = hashlib.sha256(item.content.encode()).hexdigest()
        result = await session.execute(
            select(SourceDocument).where(
                SourceDocument.workspace_id == workspace_id,
                SourceDocument.connector_id == connector_id,
                SourceDocument.external_id == item.external_id,
            )
        )
        document = result.scalar_one_or_none()
        if document is not None and document.content_hash == content_hash:
            return

        now = datetime.now(UTC)
        if document is None:
            document = SourceDocument(
                workspace_id=workspace_id,
                connector_id=connector_id,
                external_id=item.external_id,
                title=item.title,
                url=item.url,
                config=item.config,
                content_hash=content_hash,
                provider_updated_at=item.provider_updated_at,
                last_synced_at=now,
            )
            session.add(document)
            await session.flush()
        else:
            document.title = item.title
            document.url = item.url
            document.config = item.config
            document.content_hash = content_hash
            document.provider_updated_at = item.provider_updated_at
            document.last_synced_at = now

        await embed_chunks(
            workspace_id=workspace_id,
            chunks=chunk_text(item.content),
            connector_id=connector_id,
            source_document_id=document.id,
            session=session,
        )

    async def search(self, workspace_id: uuid.UUID, query: str, top_k: int) -> list:
        raise NotImplementedError("Use retrieve() for search")

    def citation(self, chunk) -> dict:
        document = getattr(chunk, "_doc", None) or getattr(chunk, "source_document", None)
        if document is None:
            return {"provider": "github", "stale": True}
        return {
            "provider": "github",
            "title": document.title,
            "url": document.url,
            "status": (document.config or {}).get("status"),
            "labels": (document.config or {}).get("labels", []),
            "updated_at": (document.config or {}).get("updated_at"),
            "stale": _is_stale(document.last_synced_at),
        }

    async def disconnect(self, workspace_id: uuid.UUID) -> None:
        async with get_session(workspace_id) as session:
            result = await session.execute(
                select(SourceConnector).where(
                    SourceConnector.workspace_id == workspace_id,
                    SourceConnector.connector_type == "github",
                )
            )
            connector = result.scalar_one_or_none()
            if connector is not None:
                connector.disconnected_at = datetime.now(UTC)

    async def purge(self, workspace_id: uuid.UUID) -> None:
        async with get_session(workspace_id) as session:
            result = await session.execute(
                select(SourceConnector).where(
                    SourceConnector.workspace_id == workspace_id,
                    SourceConnector.connector_type == "github",
                )
            )
            connector = result.scalar_one_or_none()
            if connector is None:
                return

            docs_result = await session.execute(
                select(SourceDocument).where(
                    SourceDocument.workspace_id == workspace_id,
                    SourceDocument.connector_id == connector.id,
                )
            )
            documents = list(docs_result.scalars())
            doc_ids = [doc.id for doc in documents]
            if doc_ids:
                chunks_result = await session.execute(
                    select(KnowledgeChunk).where(
                        KnowledgeChunk.workspace_id == workspace_id,
                        KnowledgeChunk.source_document_id.in_(doc_ids),
                    )
                )
                for chunk in chunks_result.scalars():
                    await session.delete(chunk)
            for document in documents:
                await session.delete(document)
