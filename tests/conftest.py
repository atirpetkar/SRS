import asyncio
import os
from collections.abc import AsyncGenerator, Generator

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from api.infra.database import Base, get_session
from api.main import create_app

# Import models to ensure they're registered
from api.v1.items import models  # noqa: F401
from api.v1.quiz import models as quiz_models  # noqa: F401
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
            
            # Create PostgreSQL functions and triggers needed for search functionality
            # This mirrors the migration but in a test-safe way
            await conn.execute(text("""
                CREATE OR REPLACE FUNCTION items_compute_search_document(
                    item_type TEXT,
                    payload JSONB,
                    tags TEXT[]
                ) RETURNS tsvector AS $$
                DECLARE
                    content_text TEXT := '';
                    tag_text TEXT := '';
                BEGIN
                    -- Extract searchable text based on item type
                    CASE item_type
                        WHEN 'flashcard' THEN
                            content_text := CONCAT_WS(' ',
                                payload->>'front',
                                payload->>'back',
                                (SELECT string_agg(value::text, ' ') FROM jsonb_array_elements_text(payload->'examples')),
                                (SELECT string_agg(value::text, ' ') FROM jsonb_array_elements_text(payload->'hints')),
                                payload->>'pronunciation'
                            );
                        WHEN 'mcq' THEN
                            content_text := CONCAT_WS(' ',
                                payload->>'stem',
                                (SELECT string_agg(value->>'text', ' ') FROM jsonb_array_elements(payload->'options') AS value),
                                (SELECT string_agg(value->>'rationale', ' ')
                                 FROM jsonb_array_elements(payload->'options') AS value
                                 WHERE value->>'rationale' IS NOT NULL)
                            );
                        WHEN 'cloze' THEN
                            content_text := CONCAT_WS(' ',
                                payload->>'text',
                                payload->>'context_note',
                                (SELECT string_agg(answer, ' ')
                                 FROM jsonb_array_elements(payload->'blanks') AS blank,
                                      jsonb_array_elements_text(blank->'answers') AS answer)
                            );
                        WHEN 'short_answer' THEN
                            content_text := CONCAT_WS(' ',
                                payload->>'prompt',
                                payload->'expected'->>'value',
                                payload->'expected'->>'unit',
                                (SELECT string_agg(value::text, ' ') FROM jsonb_array_elements_text(payload->'acceptable_patterns'))
                            );
                        ELSE
                            content_text := payload::text;
                    END CASE;
                    
                    -- Convert tags array to text
                    tag_text := COALESCE(array_to_string(tags, ' '), '');
                    
                    -- Return weighted tsvector
                    RETURN
                        setweight(to_tsvector('english', COALESCE(content_text, '')), 'A') ||
                        setweight(to_tsvector('english', tag_text), 'B') ||
                        setweight(to_tsvector('english', item_type), 'C');
                END;
                $$ LANGUAGE plpgsql IMMUTABLE;
            """))
            
            await conn.execute(text("""
                CREATE OR REPLACE FUNCTION items_update_search_document()
                RETURNS trigger AS $$
                BEGIN
                    NEW.search_document := items_compute_search_document(NEW.type, NEW.payload, NEW.tags);
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql;
            """))
            
            await conn.execute(text("""
                CREATE TRIGGER items_search_document_trigger
                    BEFORE INSERT OR UPDATE OF type, payload, tags ON items
                    FOR EACH ROW EXECUTE FUNCTION items_update_search_document();
            """))

        yield engine

        await engine.dispose()
    else:
        # Skip database tests if no PostgreSQL available
        pytest.skip("No PostgreSQL database available for testing")


@pytest.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create a fresh database session for each test."""
    async with AsyncSession(test_engine, expire_on_commit=False) as session:
        yield session
        # Clean up data after each test while preserving schema
        await session.rollback()
        await session.execute(text("DELETE FROM results"))
        await session.execute(text("DELETE FROM quiz_items"))
        await session.execute(text("DELETE FROM quizzes"))
        await session.execute(text("DELETE FROM reviews"))
        await session.execute(text("DELETE FROM scheduler_state"))
        await session.execute(text("DELETE FROM items"))
        await session.execute(text("DELETE FROM users"))
        await session.execute(text("DELETE FROM orgs"))
        await session.execute(text("DELETE FROM sources"))
        await session.execute(text("DELETE FROM media_assets"))
        await session.commit()


@pytest.fixture
def app(db_session, sample_user, sample_org):
    """Create a test FastAPI application with test database."""
    from api.v1.core.security import Principal, get_principal

    app = create_app()

    # Override the database dependency
    app.dependency_overrides[get_session] = lambda: db_session

    # Override the principal dependency using actual test entities
    def get_test_principal():
        return Principal(
            user_id=str(sample_user.id),
            org_id=str(sample_org.id),
            roles=["admin"],
            email=sample_user.email,
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

    org = Organization(id=org_uuid, name="Test Organization")
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)
    return org


@pytest.fixture
async def sample_user(db_session: AsyncSession, sample_org):
    """Create a sample user for testing."""
    import random
    import uuid

    from api.v1.items.models import User

    # Use fixed user ID that matches the principal override
    user_id = "test_user_123"
    user_uuid = uuid.uuid5(uuid.NAMESPACE_DNS, user_id)

    # Use unique email per test to avoid conflicts
    unique_email = f"test_{random.randint(1000, 9999)}@example.com"

    user = User(id=user_uuid, email=unique_email, org_id=sample_org.id)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def sample_org_and_user(sample_org, sample_user):
    """Provide both org and user as a tuple for convenience."""
    return str(sample_org.id), str(sample_user.id)
