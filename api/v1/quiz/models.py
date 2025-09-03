from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from api.infra.database import Base


class Quiz(Base):
    """Quiz session entity - tracks quiz instances with mode and params."""

    __tablename__ = "quizzes"

    id: Mapped[UUID] = mapped_column(PG_UUID, primary_key=True, default=uuid4)
    org_id: Mapped[UUID] = mapped_column(PG_UUID, ForeignKey("orgs.id"), nullable=False)
    user_id: Mapped[UUID] = mapped_column(PG_UUID, nullable=False)
    mode: Mapped[str] = mapped_column(String(20), nullable=False)  # review, drill, mock
    params: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, server_default="{}"
    )
    started_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))

    # Relationships
    organization: Mapped["Organization"] = relationship("Organization")
    quiz_items: Mapped[list["QuizItem"]] = relationship(
        back_populates="quiz", cascade="all, delete-orphan"
    )
    result: Mapped["Result | None"] = relationship(
        back_populates="quiz", cascade="all, delete-orphan", uselist=False
    )

    # Constraints
    __table_args__ = (
        CheckConstraint("mode IN ('review', 'drill', 'mock')", name="quiz_mode_check"),
    )


class QuizItem(Base):
    """Quiz item association - tracks items in a quiz with position."""

    __tablename__ = "quiz_items"

    quiz_id: Mapped[UUID] = mapped_column(
        PG_UUID, ForeignKey("quizzes.id", ondelete="CASCADE"), primary_key=True
    )
    item_id: Mapped[UUID] = mapped_column(
        PG_UUID, ForeignKey("items.id"), primary_key=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    # Relationships
    quiz: Mapped["Quiz"] = relationship(back_populates="quiz_items")
    item: Mapped["Item"] = relationship("Item")

    # Constraints
    __table_args__ = (
        UniqueConstraint("quiz_id", "position", name="quiz_items_quiz_position_unique"),
    )


class Result(Base):
    """Quiz result entity - tracks final scores and breakdown."""

    __tablename__ = "results"

    quiz_id: Mapped[UUID] = mapped_column(
        PG_UUID, ForeignKey("quizzes.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[UUID] = mapped_column(PG_UUID, primary_key=True)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    breakdown: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, server_default="{}"
    )

    # Relationships
    quiz: Mapped["Quiz"] = relationship(back_populates="result")
