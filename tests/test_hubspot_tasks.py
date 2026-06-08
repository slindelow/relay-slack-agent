from datetime import UTC, datetime, timedelta
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select, text

from relay.config import get_settings
from relay.crypto import encrypt_token
from relay.db.models import CrmConnection, CustomerAccount
from relay.slack.oauth import upsert_workspace_from_install
from relay.worker.hubspot_tasks import _sync_hubspot_accounts_async


@pytest.mark.asyncio
async def test_sync_hubspot_accounts_upserts_customer_accounts(db_session, relay_settings):
    workspace = await upsert_workspace_from_install(db_session, "T_HUB_SYNC", "Hub Sync")
    await db_session.flush()
    await db_session.execute(
        text("SELECT set_config('app.current_workspace_id', :workspace_id, true)"),
        {"workspace_id": str(workspace.id)},
    )

    key = get_settings().token_encryption_key_bytes
    encrypted_access_token, access_nonce = encrypt_token("hub-access-token", key)
    connection = CrmConnection(
        workspace_id=workspace.id,
        crm_provider="hubspot",
        encrypted_access_token=encrypted_access_token,
        encrypted_access_token_nonce=access_nonce,
        scopes="crm.objects.companies.read",
        hubspot_portal_id="12345",
        access_token_expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    db_session.add(connection)
    await db_session.flush()

    companies = [
        {
            "id": "101",
            "properties": {
                "name": "Acme Corp",
                "domain": "acme.example",
                "hs_lead_status": "customer",
                "dealtype": "newbusiness",
            },
        },
        {
            "id": "102",
            "properties": {
                "name": "Beta Inc",
                "domain": "beta.example",
            },
        },
    ]

    @asynccontextmanager
    async def fake_get_session(workspace_id=None):
        yield db_session

    with (
        patch("relay.db.session.get_session", fake_get_session),
        patch("relay.integrations.hubspot.fetch_hubspot_companies", new=AsyncMock(return_value=companies)),
    ):
        await _sync_hubspot_accounts_async(str(workspace.id))

    result = await db_session.execute(
        select(CustomerAccount).where(
            CustomerAccount.workspace_id == workspace.id,
            CustomerAccount.crm_provider == "hubspot",
        )
    )
    accounts = {account.external_crm_id: account for account in result.scalars()}

    assert set(accounts) == {"101", "102"}
    assert accounts["101"].name == "Acme Corp"
    assert accounts["101"].domain == "acme.example"
    assert accounts["101"].external_crm_url == "https://app.hubspot.com/contacts/12345/company/101"
    assert accounts["101"].tier == "starter"
    assert accounts["101"].lifecycle_stage == "customer"

    await db_session.refresh(connection)
    assert connection.sync_status == "synced"
    assert connection.last_synced_at is not None


@pytest.mark.asyncio
async def test_sync_hubspot_accounts_updates_existing_customer_account(db_session, relay_settings):
    workspace = await upsert_workspace_from_install(db_session, "T_HUB_UPDATE", "Hub Update")
    await db_session.flush()
    await db_session.execute(
        text("SELECT set_config('app.current_workspace_id', :workspace_id, true)"),
        {"workspace_id": str(workspace.id)},
    )

    key = get_settings().token_encryption_key_bytes
    encrypted_access_token, access_nonce = encrypt_token("hub-access-token", key)
    connection = CrmConnection(
        workspace_id=workspace.id,
        crm_provider="hubspot",
        encrypted_access_token=encrypted_access_token,
        encrypted_access_token_nonce=access_nonce,
        scopes="crm.objects.companies.read",
        hubspot_portal_id="12345",
    )
    db_session.add(connection)
    db_session.add(
        CustomerAccount(
            workspace_id=workspace.id,
            name="Old Name",
            domain="old.example",
            crm_provider="hubspot",
            external_crm_id="101",
            tier="enterprise",
        )
    )
    await db_session.flush()

    companies = [
        {
            "id": "101",
            "properties": {
                "name": "New Name",
                "domain": "new.example",
                "hs_lead_status": "active",
            },
        }
    ]

    @asynccontextmanager
    async def fake_get_session(workspace_id=None):
        yield db_session

    with (
        patch("relay.db.session.get_session", fake_get_session),
        patch("relay.integrations.hubspot.fetch_hubspot_companies", new=AsyncMock(return_value=companies)),
    ):
        await _sync_hubspot_accounts_async(str(workspace.id))

    result = await db_session.execute(
        select(CustomerAccount).where(
            CustomerAccount.workspace_id == workspace.id,
            CustomerAccount.external_crm_id == "101",
        )
    )
    account = result.scalar_one()
    assert account.name == "New Name"
    assert account.domain == "new.example"
    assert account.tier == "enterprise"
