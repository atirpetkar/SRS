import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from api.main import create_app
from api.infra.database import Base, get_session
from api.config.settings import settings


@pytest.fixture
def app():
    """Create a test FastAPI application."""
    return create_app()


@pytest.fixture
def client(app):
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
async def async_client(app):
    """Create an async test client."""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def auth_headers():
    """Default auth headers for testing."""
    return {
        "X-User-ID": "test_user",
        "X-Org-ID": "test_org",
    }


@pytest.fixture
def mock_principal():
    """Mock principal for testing."""
    from api.v1.core.security import Principal

    return Principal(
        user_id="test_user",
        org_id="test_org",
        roles=["admin"],
        email="test@example.com",
    )
