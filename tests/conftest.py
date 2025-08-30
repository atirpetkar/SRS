import asyncio
import os
from collections.abc import AsyncGenerator, Generator

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from api.infra.database import Base, get_session
from api.main import create_app

# Import models to ensure they're registered
from api.v1.items import models  # noqa: F401
from api.v1.review import models as review_models  # noqa: F401


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
def app(db_session, sample_user, sample_org):
    """Create a test FastAPI application with test database."""
    from api.v1.core.security import get_principal, Principal
    
    app = create_app()

    # Override the database dependency
    app.dependency_overrides[get_session] = lambda: db_session
    
    # Override the principal dependency using actual test entities
    def get_test_principal():
        return Principal(
            user_id=str(sample_user.id),
            org_id=str(sample_org.id), 
            roles=["admin"],
            email=sample_user.email
        )
    
    app.dependency_overrides[get_principal] = get_test_principal

    yield app

    # Clean up
    app.dependency_overrides.clear()


@pytest.fixture
def simple_app():
    """Create a simple test FastAPI application without database dependencies."""
    return create_app()


@pytest.fixture
def client(app) -> Generator[TestClient, None, None]:
    """Create a test client."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def simple_client(simple_app) -> Generator[TestClient, None, None]:
    """Create a simple test client without database dependencies."""
    with TestClient(simple_app) as test_client:
        yield test_client


@pytest.fixture
async def async_client(app) -> AsyncGenerator[AsyncClient, None]:
    """Create an async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
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


@pytest.fixture
async def sample_org(db_session: AsyncSession):
    """Create a sample organization for testing."""
    from api.v1.items.models import Organization
    
    # Use fixed UUID that matches the principal override
    org_id = "test_org_123"
    
    # Use a UUID-like string for the actual database
    import uuid
    org_uuid = uuid.uuid5(uuid.NAMESPACE_DNS, org_id)
    
    org = Organization(
        id=org_uuid,
        name="Test Organization"
    )
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)
    return org


@pytest.fixture
async def sample_user(db_session: AsyncSession, sample_org):
    """Create a sample user for testing."""
    from api.v1.items.models import User
    import uuid
    import random
    
    # Use fixed user ID that matches the principal override
    user_id = "test_user_123"
    user_uuid = uuid.uuid5(uuid.NAMESPACE_DNS, user_id)
    
    # Use unique email per test to avoid conflicts
    unique_email = f"test_{random.randint(1000, 9999)}@example.com"
    
    user = User(
        id=user_uuid,
        email=unique_email,
        org_id=sample_org.id
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user
