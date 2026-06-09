"""Google Drive source connector for RELAY.

Syncs files from a configured Drive folder into knowledge_chunks.
Credentials are stored encrypted in source_connectors.encrypted_credentials
as a JSON-serialised dict: {access_token, refresh_token, token_uri, client_id, client_secret}.
For local dev, GOOGLE_DRIVE_CREDENTIALS_JSON env var is used as a fallback.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime

from sqlalchemy import select

from relay.connectors.base import Connector
from relay.connectors.chunking import chunk_text
from relay.connectors.embeddings import embed_chunks
from relay.crypto import decrypt_token, kms_provider_from_settings, workspace_encryption_key
from relay.db.models import KnowledgeChunk, SourceConnector, SourceDocument, Workspace
from relay.db.session import get_session
from relay.config import get_settings


def _build_drive_service(credentials_json: str):
    """Build an authenticated Google Drive API service from credential JSON."""
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds_dict = json.loads(credentials_json)
    creds = Credentials(
        token=creds_dict.get("access_token"),
        refresh_token=creds_dict.get("refresh_token"),
        token_uri=creds_dict.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=creds_dict.get("client_id"),
        client_secret=creds_dict.get("client_secret"),
    )
    return build("drive", "v3", credentials=creds, cache_discovery=False)


class GoogleDriveConnector(Connector):
    """Syncs a Google Drive folder into RELAY knowledge_chunks."""

    async def sync(self, workspace_id: uuid.UUID, connector_id: uuid.UUID) -> None:
        settings = get_settings()
        async with get_session(workspace_id) as session:
            result = await session.execute(
                select(SourceConnector).where(
                    SourceConnector.workspace_id == workspace_id,
                    SourceConnector.id == connector_id,
                    SourceConnector.connector_type == "google_drive",
                    SourceConnector.disconnected_at.is_(None),
                )
            )
            connector_row = result.scalar_one_or_none()
            if connector_row is None:
                return

            key_bytes = settings.token_encryption_key_bytes
            kms_provider = kms_provider_from_settings(settings)
            if kms_provider is not None:
                workspace_result = await session.execute(select(Workspace).where(Workspace.id == workspace_id))
                workspace = workspace_result.scalar_one()
                key_bytes = workspace_encryption_key(workspace, key_bytes, kms_provider)

            credentials_json = decrypt_token(
                connector_row.encrypted_credentials,
                connector_row.encrypted_credentials_nonce,
                key_bytes,
            )
            folder_id = connector_row.config.get("folder_id")
            if not folder_id:
                return

            service = _build_drive_service(credentials_json)

            response = (
                service.files()
                .list(
                    q=f"'{folder_id}' in parents and trashed=false",
                    fields="files(id,name,mimeType,modifiedTime)",
                    pageSize=1000,
                )
                .execute()
            )
            files = response.get("files", [])
            for file in files:
                file_id: str = file["id"]
                title: str = file["name"]
                mime_type: str = file["mimeType"]
                modified_time_str: str | None = file.get("modifiedTime")
                provider_updated_at: datetime | None = None
                if modified_time_str:
                    provider_updated_at = datetime.fromisoformat(
                        modified_time_str.replace("Z", "+00:00")
                    )

                # Export as plain text
                try:
                    if mime_type == "application/vnd.google-apps.document":
                        content_bytes = (
                            service.files()
                            .export(fileId=file_id, mimeType="text/plain")
                            .execute()
                        )
                    else:
                        content_bytes = (
                            service.files().get_media(fileId=file_id).execute()
                        )
                    content = content_bytes.decode("utf-8", errors="replace")
                except Exception:
                    continue

                content_hash = hashlib.sha256(content.encode()).hexdigest()

                # Check if unchanged
                doc_result = await session.execute(
                    select(SourceDocument).where(
                        SourceDocument.workspace_id == workspace_id,
                        SourceDocument.connector_id == connector_id,
                        SourceDocument.external_id == file_id,
                    )
                )
                doc = doc_result.scalar_one_or_none()
                if doc is not None and doc.content_hash == content_hash:
                    continue  # unchanged — skip re-embed

                if doc is None:
                    doc = SourceDocument(
                        workspace_id=workspace_id,
                        connector_id=connector_id,
                        external_id=file_id,
                        title=title,
                        content_hash=content_hash,
                        provider_updated_at=provider_updated_at,
                        last_synced_at=datetime.now(UTC),
                    )
                    session.add(doc)
                    await session.flush()
                else:
                    doc.content_hash = content_hash
                    doc.provider_updated_at = provider_updated_at
                    doc.last_synced_at = datetime.now(UTC)

                chunks = chunk_text(content)
                await embed_chunks(
                    workspace_id=workspace_id,
                    chunks=chunks,
                    connector_id=connector_id,
                    source_document_id=doc.id,
                    session=session,
                )

    async def search(self, workspace_id: uuid.UUID, query: str, top_k: int) -> list:
        raise NotImplementedError("Use retrieve() for search")

    def citation(self, chunk) -> dict:
        raise NotImplementedError("Use retrieve() for search")

    async def disconnect(self, workspace_id: uuid.UUID) -> None:
        async with get_session(workspace_id) as session:
            result = await session.execute(
                select(SourceConnector).where(
                    SourceConnector.workspace_id == workspace_id,
                    SourceConnector.connector_type == "google_drive",
                )
            )
            row = result.scalar_one_or_none()
            if row:
                row.disconnected_at = datetime.now(UTC)

    async def purge(self, workspace_id: uuid.UUID) -> None:
        async with get_session(workspace_id) as session:
            result = await session.execute(
                select(SourceConnector).where(
                    SourceConnector.workspace_id == workspace_id,
                    SourceConnector.connector_type == "google_drive",
                )
            )
            connector_row = result.scalar_one_or_none()
            if connector_row is None:
                return

            connector_id = connector_row.id

            docs_result = await session.execute(
                select(SourceDocument).where(
                    SourceDocument.workspace_id == workspace_id,
                    SourceDocument.connector_id == connector_id,
                )
            )
            doc_ids = [d.id for d in docs_result.scalars()]

            if doc_ids:
                chunks_result = await session.execute(
                    select(KnowledgeChunk).where(
                        KnowledgeChunk.workspace_id == workspace_id,
                        KnowledgeChunk.source_document_id.in_(doc_ids),
                    )
                )
                for chunk in chunks_result.scalars():
                    await session.delete(chunk)

                docs_result2 = await session.execute(
                    select(SourceDocument).where(
                        SourceDocument.workspace_id == workspace_id,
                        SourceDocument.connector_id == connector_id,
                    )
                )
                for doc in docs_result2.scalars():
                    await session.delete(doc)
