from unittest.mock import patch

import pytest
from fastapi import HTTPException

from api.config.settings import AuthMode
from api.v1.core.security import Principal, get_principal


@pytest.mark.asyncio
async def test_get_principal_auth_mode_none():
    """Test get_principal with AUTH_MODE=none returns dev defaults."""
    with patch("api.v1.core.security.settings.auth_mode", AuthMode.NONE):
        principal = await get_principal()

        assert isinstance(principal, Principal)
        assert principal.user_id == "00000000-0000-0000-0000-000000000002"
        assert principal.org_id == "00000000-0000-0000-0000-000000000001"
        assert principal.roles == ["admin"]
        assert principal.email is None


@pytest.mark.asyncio
async def test_get_principal_auth_mode_dev_requires_headers():
    """Test get_principal with AUTH_MODE=dev requires headers."""
    with patch("api.v1.core.security.settings.auth_mode", AuthMode.DEV):
        # Test missing headers - pass None explicitly since we're bypassing FastAPI DI
        with pytest.raises(HTTPException) as exc_info:
            await get_principal(x_user_id=None, x_org_id=None)
        assert exc_info.value.status_code == 400
        assert "X-User-ID and X-Org-ID headers are required" in str(
            exc_info.value.detail
        )

        # Test with headers - should work
        principal = await get_principal(x_user_id="test-user", x_org_id="test-org")
        assert principal.user_id == "test-user"
        assert principal.org_id == "test-org"
        assert principal.roles == ["admin"]


@pytest.mark.asyncio
async def test_get_principal_auth_mode_oidc_not_implemented():
    """Test get_principal with AUTH_MODE=oidc raises NotImplementedError."""
    with patch("api.v1.core.security.settings.auth_mode", AuthMode.OIDC):
        with pytest.raises(NotImplementedError, match="OIDC auth mode not implemented"):
            await get_principal()


@pytest.mark.asyncio
async def test_get_principal_unknown_auth_mode():
    """Test get_principal with unknown auth mode raises ValueError."""
    with patch("api.v1.core.security.settings.auth_mode", "invalid_mode"):
        with pytest.raises(ValueError, match="Unknown auth mode: invalid_mode"):
            await get_principal()


def test_principal_dataclass():
    """Test Principal dataclass functionality."""
    principal = Principal(
        user_id="user123",
        org_id="org456",
        roles=["user", "admin"],
        email="test@example.com",
    )

    assert principal.user_id == "user123"
    assert principal.org_id == "org456"
    assert principal.roles == ["user", "admin"]
    assert principal.email == "test@example.com"


def test_principal_dataclass_optional_email():
    """Test Principal dataclass with optional email field."""
    principal = Principal(user_id="user123", org_id="org456", roles=["user"])

    assert principal.user_id == "user123"
    assert principal.org_id == "org456"
    assert principal.roles == ["user"]
    assert principal.email is None
