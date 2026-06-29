"""Celery tasks for HubSpot sync."""

import asyncio
import logging
from uuid import UUID

from relay.worker.celery_app import celery

logger = logging.getLogger(__name__)


def _parse_arr(value) -> float | None:
    """Parse a HubSpot ``annualrevenue`` property into a float, or None.

    HubSpot returns the value as a string (e.g. ``"1500000"``) or null. Any
    blank or non-numeric value is treated as "no ARR" rather than an error so a
    single malformed company never fails the whole sync.
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


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


@celery.task(name="relay.sync_all_hubspot_accounts", bind=True, max_retries=0)
def sync_all_hubspot_accounts(self) -> None:
    """Enqueue a HubSpot sync for every workspace with an active connection.

    Run on a schedule so newly added HubSpot companies flow into RELAY without
    anyone re-connecting from /relay settings.
    """
    asyncio.run(_sync_all_hubspot_accounts_async())


async def _sync_all_hubspot_accounts_async() -> None:
    from sqlalchemy import select

    from relay.db.models import CrmConnection
    from relay.db.session import get_session

    async with get_session() as session:
        result = await session.execute(
            select(CrmConnection.workspace_id).where(
                CrmConnection.crm_provider == "hubspot",
                CrmConnection.disconnected_at.is_(None),
            )
        )
        workspace_ids = [row.workspace_id for row in result.fetchall()]

    for ws_id in workspace_ids:
        sync_hubspot_accounts.delay(str(ws_id))
        logger.info("sync_all_hubspot_accounts: enqueued workspace %s", ws_id)


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

        upserted = 0
        for company in companies:
            if await _upsert_hubspot_company(
                session=session,
                workspace_id=ws_uuid,
                connection=connection,
                company=company,
            ):
                upserted += 1

        # Update sync status
        now = datetime.now(tz=timezone.utc)
        connection.last_synced_at = now
        connection.sync_status = "synced"

        logger.info(
            "sync_hubspot_accounts completed for workspace_id=%s upserted=%d",
            workspace_id,
            upserted,
        )


async def _upsert_hubspot_company(
    *,
    session,
    workspace_id: UUID,
    connection,
    company: dict,
) -> bool:
    from sqlalchemy import select

    from relay.db.models import CustomerAccount

    external_id = str(company.get("id") or "").strip()
    if not external_id:
        logger.warning("Skipping HubSpot company without id workspace_id=%s", workspace_id)
        return False

    props = company.get("properties") or {}
    name = (props.get("name") or props.get("domain") or f"HubSpot company {external_id}").strip()
    domain = (props.get("domain") or "").strip() or None
    arr = _parse_arr(props.get("annualrevenue"))
    portal_id = connection.hubspot_portal_id or "unknown"
    external_url = f"https://app.hubspot.com/contacts/{portal_id}/company/{external_id}"

    result = await session.execute(
        select(CustomerAccount).where(
            CustomerAccount.workspace_id == workspace_id,
            CustomerAccount.crm_provider == "hubspot",
            CustomerAccount.external_crm_id == external_id,
            CustomerAccount.deleted_at.is_(None),
        )
    )
    account = result.scalar_one_or_none()

    account_context = {
        "hubspot": {
            "hs_lead_status": props.get("hs_lead_status"),
            "dealtype": props.get("dealtype"),
            "createdate": props.get("createdate"),
            "hs_analytics_source": props.get("hs_analytics_source"),
        }
    }

    if account is None:
        account = CustomerAccount(
            workspace_id=workspace_id,
            name=name,
            domain=domain,
            crm_provider="hubspot",
            external_crm_id=external_id,
            external_crm_url=external_url,
            tier="starter",
            lifecycle_stage=props.get("hs_lead_status"),
            arr=arr,
            account_context=account_context,
        )
        session.add(account)
        await session.flush()
        return True

    account.name = name
    account.domain = domain
    account.external_crm_url = external_url
    account.lifecycle_stage = props.get("hs_lead_status")
    if arr is not None:
        account.arr = arr
    account.account_context = account_context
    return True
