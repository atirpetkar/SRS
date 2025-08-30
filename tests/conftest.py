import asyncio
import os
from collections.abc import AsyncGenerator, Generator

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import StaticPool

from api.infra.database import Base, get_session
from api.main import create_app

# Import models to ensure they're registered
from api.v1.items import models  # noqa: F401


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def test_engine():
    """Create a test database engine."""
    database_url = os.getenv("DATABASE_URL")
    
    if database_url and "postgresql" in database_url:
        # Use the CI PostgreSQL database
        engine = create_async_engine(database_url, echo=False)
        
        # Create all tables
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        
        yield engine
        
        # Clean up: drop all tables
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        
        await engine.dispose()
    else:
        # Skip database tests if no PostgreSQL available
        pytest.skip("No PostgreSQL database available for testing")


@pytest.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create a fresh database session for each test."""
    async with AsyncSession(test_engine, expire_on_commit=False) as session:
        yield session
        # Rollback any changes after each test
        await session.rollback()


@pytest.fixture
def app(db_session):
    """Create a test FastAPI application with test database."""
    app = create_app()
    
    # Override the database dependency
    app.dependency_overrides[get_session] = lambda: db_session
    
    yield app
    
    # Clean up
    app.dependency_overrides.clear()


@pytest.fixture
def client(app) -> Generator[TestClient, None, None]:
    """Create a test client."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
async def async_client(app) -> AsyncGenerator[AsyncClient, None]:
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
