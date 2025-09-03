"""
Idempotency support for preventing duplicate requests.
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import Header
from sqlalchemy import JSON, Integer, String, delete
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func, select

from api.infra.database import Base
from api.v1.core.security import Principal


class IdempotencyKey(Base):
    """Idempotency key storage for preventing duplicate operations."""

    __tablename__ = "idempotency_keys"

    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    endpoint: Mapped[str] = mapped_column(String(100), nullable=False)
    org_id: Mapped[UUID] = mapped_column(PG_UUID, nullable=False)
    user_id: Mapped[UUID] = mapped_column(PG_UUID, nullable=False)
    response_data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )


class IdempotencyService:
    """Service for handling idempotency keys and duplicate request detection."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def check_idempotency_key(
        self, key: str, endpoint: str, principal: Principal
    ) -> tuple[bool, dict[str, Any], int] | None:
        """
        Check if idempotency key exists and return cached response if found.

        Returns:
            None if key not found (new request)
            (True, response_data, status_code) if key found and not expired
        """
        # Clean up expired keys first
        await self._cleanup_expired_keys()

        # Look for existing key
        stmt = select(IdempotencyKey).where(
            IdempotencyKey.key == key,
            IdempotencyKey.endpoint == endpoint,
            IdempotencyKey.org_id == principal.org_uuid,
            IdempotencyKey.user_id == principal.user_uuid,
            IdempotencyKey.expires_at > datetime.now(UTC),
        )

        result = await self.session.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            return True, existing.response_data, existing.status_code

        return None

    async def store_idempotency_key(
        self,
        key: str,
        endpoint: str,
        principal: Principal,
        response_data: dict[str, Any],
        status_code: int,
        ttl_hours: int = 24,
    ) -> None:
        """
        Store idempotency key with response data for future requests.

        Args:
            key: Idempotency key from request header
            endpoint: API endpoint identifier
            principal: Current user principal
            response_data: Response data to cache
            status_code: HTTP status code
            ttl_hours: Time to live in hours (default 24)
        """
        expires_at = datetime.now(UTC) + timedelta(hours=ttl_hours)

        idempotency_record = IdempotencyKey(
            key=key,
            endpoint=endpoint,
            org_id=principal.org_uuid,
            user_id=principal.user_uuid,
            response_data=response_data,
            status_code=status_code,
            expires_at=expires_at,
        )

        self.session.add(idempotency_record)
        await self.session.commit()

    async def _cleanup_expired_keys(self) -> None:
        """Remove expired idempotency keys from the database."""
        stmt = delete(IdempotencyKey).where(
            IdempotencyKey.expires_at <= datetime.now(UTC)
        )
        await self.session.execute(stmt)
        await self.session.commit()


def get_idempotency_key(
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
) -> str | None:
    """Extract idempotency key from request headers."""
    return idempotency_key


async def handle_idempotent_request(
    session: AsyncSession,
    principal: Principal,
    endpoint: str,
    idempotency_key: str | None,
    handler_func,
    *args,
    **kwargs,
) -> tuple[dict[str, Any], int]:
    """
    Handle an idempotent request with automatic key checking and storage.

    Args:
        session: Database session
        principal: Current user principal
        endpoint: API endpoint identifier
        idempotency_key: Idempotency key from headers (optional)
        handler_func: Function to call for processing the request
        *args, **kwargs: Arguments to pass to handler_func

    Returns:
        (response_data, status_code) tuple
    """
    service = IdempotencyService(session)

    # Check for existing idempotency key
    if idempotency_key:
        cached_response = await service.check_idempotency_key(
            idempotency_key, endpoint, principal
        )
        if cached_response:
            _, response_data, status_code = cached_response
            return response_data, status_code

    # Process the request
    response_data, status_code = await handler_func(*args, **kwargs)

    # Store the response for future duplicate requests
    if idempotency_key:
        await service.store_idempotency_key(
            idempotency_key, endpoint, principal, response_data, status_code
        )

    return response_data, status_code
