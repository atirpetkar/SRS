"""
Database models for Step 8 - Embeddings and Search.

Defines the ItemEmbedding model and related database entities.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import ARRAY, JSON, Float, ForeignKey, Text
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from api.infra.database import Base


class ItemEmbedding(Base):
    """
    Item embeddings table for vector similarity search.

    Stores precomputed embeddings with model versioning support
    and efficient HNSW indexing for similarity queries.
    """

    __tablename__ = "item_embeddings"

    # Primary key - one embedding per item
    item_id: Mapped[UUID] = mapped_column(
        PG_UUID, ForeignKey("items.id", ondelete="CASCADE"), primary_key=True
    )

    # Vector data - stored as ARRAY(Float) in SQLAlchemy, but actual column is vector(768)
    # The migration creates the proper vector(768) column type
    embedding: Mapped[list[float]] = mapped_column(ARRAY(Float), nullable=False)

    # Model metadata for versioning and migration
    model_version: Mapped[str] = mapped_column(Text, nullable=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )

    # Extensible metadata (renamed to avoid SQLAlchemy conflict)
    meta: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSON,
        default=dict,
        server_default="{}",  # Column name in database
    )

    # Relationship back to item
    item: Mapped["Item"] = relationship("Item", back_populates="embedding")

    def __repr__(self) -> str:
        return f"<ItemEmbedding(item_id={self.item_id}, model={self.model_version})>"
