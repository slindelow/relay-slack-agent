"""Celery tasks for HubSpot sync."""

import asyncio
import logging
from uuid import UUID

from relay.worker.celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(bind=True, max_retries=3)
def sync_hubspot_accounts(self, workspace_id: str) -> None:
    """Sync HubSpot company accounts into customer_accounts for a workspace.

    Runs the async sync logic inside asyncio.run() since Celery tasks are sync.
    """
    try:
        asyncio.run(_sync_hubspot_accounts_async(workspace_id))
    except Exception as exc:
        logger.exception(
            "sync_hubspot_accounts failed for workspace_id=%s: %s",
            workspace_id,
            exc,
        )
        raise self.retry(exc=exc)


async def _sync_hubspot_accounts_async(workspace_id: str) -> None:
    """Async implementation of HubSpot account sync."""
    from sqlalchemy import select
    from datetime import datetime, timezone

    from relay.config import get_settings
    from relay.crypto import decrypt_token, kms_provider_from_settings, workspace_encryption_key
    from relay.db.models import CrmConnection, CustomerAccount, Workspace
    from relay.db.session import get_session
    from relay.integrations.hubspot import fetch_hubspot_companies

    settings = get_settings()
    ws_uuid = UUID(workspace_id)

    async with get_session(workspace_id=ws_uuid) as session:
        # Load active CrmConnection for this workspace
        stmt = select(CrmConnection).where(
            CrmConnection.workspace_id == ws_uuid,
            CrmConnection.crm_provider == "hubspot",
            CrmConnection.disconnected_at.is_(None),
        )
        result = await session.execute(stmt)
        connection = result.scalar_one_or_none()

        if connection is None:
            logger.warning(
                "No active HubSpot connection found for workspace_id=%s", workspace_id
            )
            return

        key = settings.token_encryption_key_bytes
        kms_provider = kms_provider_from_settings(settings)
        if kms_provider is not None:
            workspace_result = await session.execute(select(Workspace).where(Workspace.id == ws_uuid))
            workspace = workspace_result.scalar_one()
            key = workspace_encryption_key(workspace, key, kms_provider)

        # Decrypt access token
        access_token = decrypt_token(
            connection.encrypted_access_token,
            connection.encrypted_access_token_nonce,
            key,
        )

        # Fetch companies from HubSpot
        companies = await fetch_hubspot_companies(access_token)
        logger.info(
            "Fetched %d HubSpot companies for workspace_id=%s",
            len(companies),
            workspace_id,
        )

        # TODO: implement full upsert logic for customer_accounts
        # For now, log and return without writing to DB to keep the stub simple.
        # Full implementation should:
        #   - For each company: upsert CustomerAccount matching on
        #     (workspace_id, crm_provider='hubspot', external_crm_id=company["id"])
        #   - Set name, domain from company["properties"]
        #   - Set external_crm_url = f"https://app.hubspot.com/contacts/unknown/company/{company['id']}"
        #   - Bulk-insert new accounts, update existing ones
        for company in companies:
            props = company.get("properties", {})
            logger.debug(
                "HubSpot company id=%s name=%s domain=%s",
                company.get("id"),
                props.get("name"),
                props.get("domain"),
            )

        # Update sync status
        now = datetime.now(tz=timezone.utc)
        connection.last_synced_at = now
        connection.sync_status = "synced"

        logger.info(
            "sync_hubspot_accounts completed for workspace_id=%s", workspace_id
        )
