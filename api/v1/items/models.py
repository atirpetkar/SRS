from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, CheckConstraint, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, TIMESTAMP, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from api.infra.database import Base


class TimestampMixin:
    """Mixin for timestamp fields."""
    
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), 
        server_default=func.now(),
        nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))


class Organization(Base, TimestampMixin):
    """Organization entity - top-level tenant boundary."""
    
    __tablename__ = "orgs"
    
    id: Mapped[UUID] = mapped_column(PG_UUID, primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    meta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, server_default='{}')
    
    # Relationships
    users: Mapped[list["User"]] = relationship(back_populates="organization", cascade="all, delete-orphan")
    items: Mapped[list["Item"]] = relationship(back_populates="organization", cascade="all, delete-orphan")
    sources: Mapped[list["Source"]] = relationship(back_populates="organization", cascade="all, delete-orphan")
    media_assets: Mapped[list["MediaAsset"]] = relationship(back_populates="organization", cascade="all, delete-orphan")


class User(Base, TimestampMixin):
    """User entity - belongs to an organization."""
    
    __tablename__ = "users"
    
    id: Mapped[UUID] = mapped_column(PG_UUID, primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    meta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, server_default='{}')
    
    # Foreign keys
    org_id: Mapped[UUID] = mapped_column(PG_UUID, ForeignKey("orgs.id"), nullable=False)
    
    # Relationships  
    organization: Mapped["Organization"] = relationship(back_populates="users")


class Source(Base, TimestampMixin):
    """Source entity - tracks original source of imported content."""
    
    __tablename__ = "sources"
    
    id: Mapped[UUID] = mapped_column(PG_UUID, primary_key=True, default=uuid4)
    uri: Mapped[str] = mapped_column(Text, nullable=False)
    attribution: Mapped[str | None] = mapped_column(Text)
    meta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, server_default='{}')
    
    # Foreign keys
    org_id: Mapped[UUID] = mapped_column(PG_UUID, ForeignKey("orgs.id"), nullable=False)
    
    # Relationships
    organization: Mapped["Organization"] = relationship(back_populates="sources")
    items: Mapped[list["Item"]] = relationship(back_populates="source")


class MediaAsset(Base, TimestampMixin):
    """Media asset entity - tracks images, audio, video files."""
    
    __tablename__ = "media_assets"
    
    id: Mapped[UUID] = mapped_column(PG_UUID, primary_key=True, default=uuid4)
    uri: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(String(50), nullable=False)  # image, audio, video, etc.
    meta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, server_default='{}')
    
    # Foreign keys
    org_id: Mapped[UUID] = mapped_column(PG_UUID, ForeignKey("orgs.id"), nullable=False)
    
    # Relationships
    organization: Mapped["Organization"] = relationship(back_populates="media_assets")


class Item(Base, TimestampMixin):
    """Core item entity - content-agnostic practice items."""
    
    __tablename__ = "items"
    
    id: Mapped[UUID] = mapped_column(PG_UUID, primary_key=True, default=uuid4)
    type: Mapped[str] = mapped_column(String(50), nullable=False)  # flashcard, mcq, cloze, short_answer
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, server_default='{}')
    difficulty: Mapped[str | None] = mapped_column(String(20))  # intro, core, stretch
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    content_hash: Mapped[str | None] = mapped_column(String(64))  # SHA-256 of canonical text
    schema_version: Mapped[int] = mapped_column(default=1, server_default='1')
    status: Mapped[str] = mapped_column(
        String(20), 
        default='draft', 
        server_default='draft'
    )
    version: Mapped[int] = mapped_column(default=1, server_default='1')
    media: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, server_default='{}')
    meta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, server_default='{}')
    created_by: Mapped[str | None] = mapped_column(Text)
    
    # Foreign keys
    org_id: Mapped[UUID] = mapped_column(PG_UUID, ForeignKey("orgs.id"), nullable=False)
    source_id: Mapped[UUID | None] = mapped_column(PG_UUID, ForeignKey("sources.id"))
    
    # Relationships
    organization: Mapped["Organization"] = relationship(back_populates="items")
    source: Mapped["Source | None"] = relationship(back_populates="items")
    
    # Constraints
    __table_args__ = (
        CheckConstraint("status IN ('draft', 'published')", name="items_status_check"),
        CheckConstraint("difficulty IS NULL OR difficulty IN ('intro', 'core', 'stretch')", name="items_difficulty_check"),
        Index("items_tags_gin", "tags", postgresql_using="gin"),
        Index("items_org_type_idx", "org_id", "type"),
        Index("items_org_status_idx", "org_id", "status"),
        Index("items_content_hash_idx", "content_hash"),
    )