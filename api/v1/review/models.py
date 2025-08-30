from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, ForeignKey, Integer, SmallInteger, String, Boolean, Float
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from api.infra.database import Base


class SchedulerState(Base):
    """Scheduler state for FSRS - tracks memory state per user/item."""
    
    __tablename__ = "scheduler_state"
    
    # Composite primary key
    user_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    item_id: Mapped[UUID] = mapped_column(PG_UUID, ForeignKey("items.id"), primary_key=True)
    
    # FSRS state variables
    stability: Mapped[float] = mapped_column(Float, nullable=False)
    difficulty: Mapped[float] = mapped_column(Float, nullable=False)
    due_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    last_interval: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reps: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lapses: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_reviewed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    
    # Metadata
    scheduler_name: Mapped[str] = mapped_column(String(50), nullable=False, default="fsrs_v6")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    
    # Relationship
    item: Mapped["Item"] = relationship("Item")


class Review(Base):
    """Review record - tracks all review attempts and outcomes."""
    
    __tablename__ = "reviews"
    
    id: Mapped[UUID] = mapped_column(PG_UUID, primary_key=True, default=uuid4)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    item_id: Mapped[UUID] = mapped_column(PG_UUID, ForeignKey("items.id"), nullable=False)
    ts: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    mode: Mapped[str] = mapped_column(String(20), nullable=False)  # review, drill, mock
    response: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    correct: Mapped[bool | None] = mapped_column(Boolean)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    latency_bucket: Mapped[int | None] = mapped_column(SmallInteger)
    ease: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-4 FSRS rating
    
    # Relationship
    item: Mapped["Item"] = relationship("Item")