"""Tests for relay/auth.py authorization helpers."""

import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.mark.asyncio
async def test_require_relay_admin_returns_true_for_admin():
    from relay.auth import require_relay_admin
    from relay.db.models import User

    admin = MagicMock(spec=User)
    admin.relay_role = "admin"
    admin.deleted_at = None

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = admin
    mock_session.execute = AsyncMock(return_value=mock_result)

    workspace_id = uuid.uuid4()
    result = await require_relay_admin(mock_session, workspace_id, "U_ADMIN")
    assert result is True


@pytest.mark.asyncio
async def test_require_relay_admin_returns_false_for_viewer():
    from relay.auth import require_relay_admin

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=mock_result)

    workspace_id = uuid.uuid4()
    result = await require_relay_admin(mock_session, workspace_id, "U_VIEWER")
    assert result is False


@pytest.mark.asyncio
async def test_require_relay_csm_returns_true_for_csm():
    from relay.auth import require_relay_csm
    from relay.db.models import User

    csm = MagicMock(spec=User)
    csm.relay_role = "csm"
    csm.deleted_at = None

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = csm
    mock_session.execute = AsyncMock(return_value=mock_result)

    workspace_id = uuid.uuid4()
    result = await require_relay_csm(mock_session, workspace_id, "U_CSM")
    assert result is True


@pytest.mark.asyncio
async def test_require_relay_csm_returns_true_for_admin():
    """Admins implicitly satisfy the CSM check."""
    from relay.auth import require_relay_csm
    from relay.db.models import User

    admin = MagicMock(spec=User)
    admin.relay_role = "admin"
    admin.deleted_at = None

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = admin
    mock_session.execute = AsyncMock(return_value=mock_result)

    workspace_id = uuid.uuid4()
    result = await require_relay_csm(mock_session, workspace_id, "U_ADMIN")
    assert result is True
