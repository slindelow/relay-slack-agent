"""Offline migration from global token key to workspace KMS envelope keys."""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import select

from relay.config import get_settings
from relay.crypto import decrypt_token, encrypt_token, ensure_workspace_dek, kms_provider_from_settings
from relay.db.models import CrmConnection, SourceConnector, Workspace, WorkspaceToken
from relay.db.session import get_session


def _reencrypt_secret(
    ciphertext: bytes,
    nonce: bytes,
    old_key: bytes,
    new_key: bytes,
) -> tuple[bytes, bytes]:
    plaintext = decrypt_token(ciphertext, nonce, old_key)
    return encrypt_token(plaintext, new_key)


def _reencrypt_optional_secret(
    ciphertext: bytes | None,
    nonce: bytes | None,
    old_key: bytes,
    new_key: bytes,
) -> tuple[bytes | None, bytes | None]:
    if ciphertext is None or nonce is None:
        return ciphertext, nonce
    return _reencrypt_secret(ciphertext, nonce, old_key, new_key)


async def _reencrypt_workspace(
    session,
    workspace: Workspace,
    *,
    old_key: bytes,
    kms_provider,
    dry_run: bool,
) -> dict[str, int | str]:
    workspace_key = old_key if dry_run else ensure_workspace_dek(workspace, old_key, kms_provider)
    summary: dict[str, int | str] = {
        "workspace_id": str(workspace.id),
        "workspace_tokens": 0,
        "crm_connections": 0,
        "source_connectors": 0,
    }

    token_result = await session.execute(
        select(WorkspaceToken).where(WorkspaceToken.workspace_id == workspace.id)
    )
    tokens = list(token_result.scalars())
    summary["workspace_tokens"] = len(tokens)
    for token in tokens:
        if not dry_run:
            token.encrypted_token, token.encrypted_token_nonce = _reencrypt_secret(
                token.encrypted_token,
                token.encrypted_token_nonce,
                old_key,
                workspace_key,
            )

    crm_result = await session.execute(
        select(CrmConnection).where(CrmConnection.workspace_id == workspace.id)
    )
    crm_connections = list(crm_result.scalars())
    summary["crm_connections"] = len(crm_connections)
    for connection in crm_connections:
        if not dry_run:
            connection.encrypted_access_token, connection.encrypted_access_token_nonce = _reencrypt_secret(
                connection.encrypted_access_token,
                connection.encrypted_access_token_nonce,
                old_key,
                workspace_key,
            )
            (
                connection.encrypted_refresh_token,
                connection.encrypted_refresh_token_nonce,
            ) = _reencrypt_optional_secret(
                connection.encrypted_refresh_token,
                connection.encrypted_refresh_token_nonce,
                old_key,
                workspace_key,
            )

    connector_result = await session.execute(
        select(SourceConnector).where(SourceConnector.workspace_id == workspace.id)
    )
    connectors = list(connector_result.scalars())
    summary["source_connectors"] = len(connectors)
    for connector in connectors:
        if not dry_run:
            connector.encrypted_credentials, connector.encrypted_credentials_nonce = _reencrypt_secret(
                connector.encrypted_credentials,
                connector.encrypted_credentials_nonce,
                old_key,
                workspace_key,
            )

    return summary


async def reencrypt_workspace_tokens(
    *,
    workspace_id: uuid.UUID | None = None,
    dry_run: bool = False,
) -> list[dict[str, int | str]]:
    settings = get_settings()
    kms_provider = kms_provider_from_settings(settings)
    if kms_provider is None:
        raise RuntimeError("KMS_PROVIDER=aws and KMS_KEY_ID are required for re-encryption")

    async with get_session() as session:
        query = select(Workspace).where(Workspace.wrapped_dek.is_(None))
        if workspace_id is not None:
            query = query.where(Workspace.id == workspace_id)
        result = await session.execute(query.order_by(Workspace.installed_at.asc()))
        workspaces = list(result.scalars())

        summaries = []
        for workspace in workspaces:
            summaries.append(
                await _reencrypt_workspace(
                    session,
                    workspace,
                    old_key=settings.token_encryption_key_bytes,
                    kms_provider=kms_provider,
                    dry_run=dry_run,
                )
            )

        return summaries


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Re-encrypt RELAY secrets from TOKEN_ENCRYPTION_KEY to per-workspace KMS DEKs.",
    )
    parser.add_argument("--workspace-id", type=uuid.UUID, default=None, help="Optional workspace UUID to migrate")
    parser.add_argument("--dry-run", action="store_true", help="Count affected rows without writing encrypted values")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    summaries = asyncio.run(
        reencrypt_workspace_tokens(
            workspace_id=args.workspace_id,
            dry_run=args.dry_run,
        )
    )
    for summary in summaries:
        print(
            "workspace_id={workspace_id} workspace_tokens={workspace_tokens} "
            "crm_connections={crm_connections} source_connectors={source_connectors}".format(**summary)
        )
    print(f"workspaces_processed={len(summaries)} dry_run={args.dry_run}")


if __name__ == "__main__":
    main()
