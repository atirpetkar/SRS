from typing import AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from api.config.settings import Settings, get_settings


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass


class Database:
    """Database connection and session management."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.engine = create_async_engine(
            settings.database_url,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_timeout=settings.db_pool_timeout,
            pool_recycle=settings.db_pool_recycle,
            echo=settings.debug,
        )
        self.SessionLocal = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    async def close(self):
        """Close database connections."""
        await self.engine.dispose()


# Global database instance
_database: Database | None = None


def get_database(settings: Settings = Depends(get_settings)) -> Database:
    """Get or create the global database instance."""
    global _database
    if _database is None:
        _database = Database(settings)
    return _database


async def get_session(
    database: Database = Depends(get_database),
) -> AsyncGenerator[AsyncSession, None]:
    """Dependency injection for database sessions."""
    async with database.SessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# Convenience type alias for dependency injection
SessionDep = Depends(get_session)