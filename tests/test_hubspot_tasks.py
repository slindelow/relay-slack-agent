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
                "annualrevenue": "1500000",
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
    assert float(accounts["101"].arr) == 1500000.0
    # Company 102 has no annualrevenue property → ARR stays unset.
    assert accounts["102"].arr is None

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
            arr=500000,
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
                "annualrevenue": "2000000",
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
    assert float(account.arr) == 2000000.0


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1500000", 1500000.0),
        ("1500000.50", 1500000.50),
        (2000000, 2000000.0),
        (None, None),
        ("", None),
        ("   ", None),
        ("not-a-number", None),
        ("9999999999.99", 9999999999.99),  # max that fits Numeric(12, 2)
        ("10000000000", None),  # overflows Numeric(12, 2) → treated as no ARR
        ("999999999999999", None),  # garbage placeholder
    ],
)
def test_parse_arr(value, expected):
    from relay.worker.hubspot_tasks import _parse_arr

    assert _parse_arr(value) == expected


@pytest.mark.asyncio
async def test_sync_all_hubspot_accounts_enqueues_each_active_workspace(db_session, relay_settings):
    from relay.worker.hubspot_tasks import _sync_all_hubspot_accounts_async

    ws1 = await upsert_workspace_from_install(db_session, "T_ALL_1", "All One")
    ws2 = await upsert_workspace_from_install(db_session, "T_ALL_2", "All Two")
    await db_session.flush()

    key = get_settings().token_encryption_key_bytes
    enc, nonce = encrypt_token("tok", key)
    for ws in (ws1, ws2):
        db_session.add(
            CrmConnection(
                workspace_id=ws.id,
                crm_provider="hubspot",
                encrypted_access_token=enc,
                encrypted_access_token_nonce=nonce,
                scopes="crm.objects.companies.read",
            )
        )
    # A disconnected connection must be skipped.
    ws3 = await upsert_workspace_from_install(db_session, "T_ALL_3", "All Three")
    await db_session.flush()
    db_session.add(
        CrmConnection(
            workspace_id=ws3.id,
            crm_provider="hubspot",
            encrypted_access_token=enc,
            encrypted_access_token_nonce=nonce,
            scopes="crm.objects.companies.read",
            disconnected_at=datetime.now(UTC),
        )
    )
    await db_session.flush()

    @asynccontextmanager
    async def fake_get_session(workspace_id=None):
        yield db_session

    enqueued: list[str] = []
    with (
        patch("relay.db.session.get_session", fake_get_session),
        patch(
            "relay.worker.hubspot_tasks.sync_hubspot_accounts.delay",
            side_effect=lambda ws_id: enqueued.append(ws_id),
        ),
    ):
        await _sync_all_hubspot_accounts_async()

    assert set(enqueued) == {str(ws1.id), str(ws2.id)}
