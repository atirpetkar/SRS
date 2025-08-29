import pytest
from fastapi.testclient import TestClient

from api.main import create_app


@pytest.fixture
def app():
    """Create a test FastAPI application."""
    return create_app()


@pytest.fixture
def client(app):
    """Create a test client."""
    return TestClient(app)


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
