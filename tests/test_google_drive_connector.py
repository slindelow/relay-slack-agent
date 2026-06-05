"""Unit tests for the Google Drive connector."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from relay.connectors.google_drive import GoogleDriveConnector


def _make_connector_row(connector_id: uuid.UUID, workspace_id: uuid.UUID, folder_id: str = "folder123"):
    from relay.crypto import encrypt_token
    creds = json.dumps({"access_token": "tok", "refresh_token": "ref", "token_uri": "https://t", "client_id": "c", "client_secret": "s"})
    key = bytes.fromhex("a" * 64)
    ciphertext, nonce = encrypt_token(creds, key)
    row = MagicMock()
    row.id = connector_id
    row.workspace_id = workspace_id
    row.connector_type = "google_drive"
    row.config = {"folder_id": folder_id}
    row.encrypted_credentials = ciphertext
    row.encrypted_credentials_nonce = nonce
    row.disconnected_at = None
    row.last_synced_at = None
    row.sync_status = "not_synced"
    return row, key


def _make_doc_row(external_id: str, content_hash: str):
    row = MagicMock()
    row.id = uuid.uuid4()
    row.external_id = external_id
    row.content_hash = content_hash
    return row


@pytest.mark.asyncio
async def test_sync_creates_source_documents_and_chunks():
    workspace_id = uuid.uuid4()
    connector_id = uuid.uuid4()
    connector_row, key = _make_connector_row(connector_id, workspace_id)
    file_content = "Some document text"
    file_content_bytes = file_content.encode()

    fake_files = [{"id": "file1", "name": "Doc1", "mimeType": "text/plain", "modifiedTime": "2024-01-01T00:00:00Z"}]
    drive_service = MagicMock()
    drive_service.files.return_value.list.return_value.execute.return_value = {"files": fake_files}
    drive_service.files.return_value.get_media.return_value.execute.return_value = file_content_bytes

    session = AsyncMock()
    session.add = MagicMock()

    # connector SELECT: returns connector_row
    # doc SELECT: returns None (new document)
    connector_result = MagicMock()
    connector_result.scalar_one_or_none.return_value = connector_row

    doc_result = MagicMock()
    doc_result.scalar_one_or_none.return_value = None

    session.execute = AsyncMock(side_effect=[connector_result, doc_result])
    session.flush = AsyncMock()

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("relay.connectors.google_drive.get_session", return_value=ctx),
        patch("relay.connectors.google_drive.get_settings") as mock_settings,
        patch("relay.connectors.google_drive._build_drive_service", return_value=drive_service),
        patch("relay.connectors.google_drive.embed_chunks", new=AsyncMock(return_value=[uuid.uuid4()])),
    ):
        mock_settings.return_value.token_encryption_key_bytes = key
        mock_settings.return_value.google_drive_credentials_json = ""
        await GoogleDriveConnector().sync(workspace_id, connector_id)

    session.add.assert_called_once()
    session.flush.assert_called()


@pytest.mark.asyncio
async def test_sync_skips_unchanged_hash():
    workspace_id = uuid.uuid4()
    connector_id = uuid.uuid4()
    connector_row, key = _make_connector_row(connector_id, workspace_id)
    file_content = "No change here"
    existing_hash = hashlib.sha256(file_content.encode()).hexdigest()

    fake_files = [{"id": "file1", "name": "Doc1", "mimeType": "text/plain", "modifiedTime": "2024-01-01T00:00:00Z"}]
    drive_service = MagicMock()
    drive_service.files.return_value.list.return_value.execute.return_value = {"files": fake_files}
    drive_service.files.return_value.get_media.return_value.execute.return_value = file_content.encode()

    doc_row = _make_doc_row("file1", existing_hash)

    session = AsyncMock()
    session.add = MagicMock()
    connector_result = MagicMock()
    connector_result.scalar_one_or_none.return_value = connector_row
    doc_result = MagicMock()
    doc_result.scalar_one_or_none.return_value = doc_row
    session.execute = AsyncMock(side_effect=[connector_result, doc_result])
    session.flush = AsyncMock()

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("relay.connectors.google_drive.get_session", return_value=ctx),
        patch("relay.connectors.google_drive.get_settings") as mock_settings,
        patch("relay.connectors.google_drive._build_drive_service", return_value=drive_service),
        patch("relay.connectors.google_drive.embed_chunks", new=AsyncMock()) as mock_embed,
    ):
        mock_settings.return_value.token_encryption_key_bytes = key
        mock_settings.return_value.google_drive_credentials_json = ""
        await GoogleDriveConnector().sync(workspace_id, connector_id)

    mock_embed.assert_not_called()


@pytest.mark.asyncio
async def test_purge_deletes_all_rows():
    workspace_id = uuid.uuid4()
    connector_id = uuid.uuid4()
    connector_row, key = _make_connector_row(connector_id, workspace_id)
    doc_id = uuid.uuid4()

    doc_row = MagicMock()
    doc_row.id = doc_id

    chunk_row = MagicMock()

    session = AsyncMock()
    connector_result = MagicMock()
    connector_result.scalar_one_or_none.return_value = connector_row

    doc_ids_result = MagicMock()
    doc_ids_result.scalars.return_value = [doc_row]

    chunks_result = MagicMock()
    chunks_result.scalars.return_value = [chunk_row]

    docs_result2 = MagicMock()
    docs_result2.scalars.return_value = [doc_row]

    session.execute = AsyncMock(side_effect=[connector_result, doc_ids_result, chunks_result, docs_result2])
    session.delete = AsyncMock()

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)

    with patch("relay.connectors.google_drive.get_session", return_value=ctx):
        await GoogleDriveConnector().purge(workspace_id)

    assert session.delete.call_count == 2
